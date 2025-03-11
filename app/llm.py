from typing import Dict, List, Literal, Optional, Union
import json
import httpx
import asyncio

from openai import (
    APIError,
    AsyncAzureOpenAI,
    AsyncOpenAI,
    AuthenticationError,
    OpenAIError,
    RateLimitError,
)
from tenacity import retry, stop_after_attempt, wait_random_exponential

from app.config import LLMSettings, config
from app.logger import logger  # Assuming a logger is set up in your app
from app.schema import Message


class HuggingFaceChatCompletions:
    """Mimics the chat.completions functionality of OpenAI but for Hugging Face."""
    
    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
    
    async def create(self, model, messages, temperature=0, max_tokens=None, tools=None, tool_choice=None, timeout=None, **kwargs):
        """Convert OpenAI-style request to Hugging Face format and handle the response."""
        # Convert messages to Hugging Face format, including tool descriptions if provided
        prompt = self._convert_messages_to_prompt(messages, tools)
        
        # Ensure temperature is positive for Hugging Face
        hf_temperature = max(0.01, temperature) if temperature is not None else 0.01
        
        # Prepare the payload
        payload = {
            "inputs": prompt,
            "parameters": {
                "temperature": hf_temperature,
                "max_new_tokens": max_tokens or 1024,
                "return_full_text": False
            }
        }
        
        # Make the API request
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self.base_url,
                    headers=self.headers,
                    json=payload,
                    timeout=timeout or 30
                )
                
                if response.status_code != 200:
                    logger.error(f"API error: Error code: {response.status_code} - {response.text}")
                    # Create a custom error that mimics OpenAI's APIError
                    error = APIError(f"Error code: {response.status_code} - {response.text}", response=response, body=response.text, request=httpx.Request("POST", self.base_url))
                    raise error
                
                # Process and convert the response to match OpenAI's format
                return self._convert_response_to_openai_format(response.json(), tools is not None)
                
            except httpx.RequestError as e:
                logger.error(f"Request error: {str(e)}")
                # Create a custom error that mimics OpenAI's APIError
                error = APIError(f"Request error: {str(e)}", response=None, body=str(e), request=httpx.Request("POST", self.base_url))
                raise error
    
    def _convert_messages_to_prompt(self, messages, tools=None):
        """Convert OpenAI-style messages to a text prompt for Hugging Face."""
        prompt = ""
        
        # Add tool descriptions to the beginning of the prompt if tools are provided
        if tools:
            prompt += "You have access to the following functions. Use them if required:\n\n"
            for tool in tools:
                if tool.get("type") == "function":
                    function = tool.get("function", {})
                    prompt += f"Function: {function.get('name')}\n"
                    prompt += f"Description: {function.get('description')}\n"
                    
                    # Add parameters
                    parameters = function.get("parameters", {})
                    if parameters:
                        prompt += "Parameters:\n"
                        properties = parameters.get("properties", {})
                        for param_name, param_details in properties.items():
                            param_type = param_details.get("type", "")
                            param_desc = param_details.get("description", "")
                            prompt += f"  - {param_name} ({param_type}): {param_desc}\n"
                        
                        # Add required parameters
                        required = parameters.get("required", [])
                        if required:
                            prompt += f"Required parameters: {', '.join(required)}\n"
                    
                    prompt += "\n"
            
            # Add explicit instructions for tool response format
            prompt += "\nWhen you need to use a function, respond in the following JSON format:\n"
            prompt += '{"function_call": {"name": "function_name", "arguments": {"arg1": "value1", "arg2": "value2"}}}\n\n'
        
        # Convert conversation messages to prompt format
        system_content = ""
        for message in messages:
            role = message.get("role", "").lower()
            content = message.get("content", "")
            
            if role == "system":
                system_content = content
            elif role == "user":
                if prompt:
                    prompt += f"<s>[INST] {content} [/INST]"
                else:
                    if system_content:
                        prompt += f"<s>[INST] <<SYS>> {system_content} <</SYS>>\n{content} [/INST]"
                    else:
                        prompt += f"<s>[INST] {content} [/INST]"
            elif role == "assistant":
                prompt += f" {content} </s>"
        
        # Ensure the prompt ends correctly
        if not prompt.endswith("[/INST]") and not prompt.endswith("</s>"):
            prompt += " [/INST]"
            
        return prompt
    
    def _convert_response_to_openai_format(self, hf_response, has_tools=False):
        """Convert Hugging Face response to OpenAI format."""
        # Extract the generated text
        generated_text = hf_response[0]["generated_text"] if isinstance(hf_response, list) else hf_response.get("generated_text", "")
        
        # Create an OpenAI-like response structure
        openai_response = type('OpenAIResponse', (), {})()
        openai_response.choices = [type('Choice', (), {})()]
        openai_response.choices[0].message = type('Message', (), {})()
        openai_response.choices[0].message.content = generated_text
        openai_response.choices[0].message.tool_calls = []  # Initialize empty tool_calls list
        
        # Handle tool calls if tools were provided
        if has_tools:
            try:
                # Look for JSON pattern in the response text that matches function calls
                import re
                
                # Try to find a JSON object that would represent a function call
                json_pattern = r'(\{.*"function_call"\s*:.*\})'
                matches = re.findall(json_pattern, generated_text, re.DOTALL)
                
                if matches:
                    for match in matches:
                        try:
                            # Try to parse the JSON
                            function_data = json.loads(match)
                            function_call = function_data.get("function_call", {})
                            
                            # Create a tool call object
                            tool_call = type('ToolCall', (), {})()
                            tool_call.id = f"call_{len(openai_response.choices[0].message.tool_calls)}"
                            tool_call.type = "function"
                            tool_call.function = type('Function', (), {})()
                            tool_call.function.name = function_call.get("name", "")
                            
                            # Handle arguments - could be a string or a dictionary
                            arguments = function_call.get("arguments", {})
                            if isinstance(arguments, dict):
                                tool_call.function.arguments = json.dumps(arguments)
                            else:
                                tool_call.function.arguments = str(arguments)
                            
                            # Add the tool call to the message
                            openai_response.choices[0].message.tool_calls.append(tool_call)
                            
                            # If we found function calls, set content to None as per OpenAI's behavior
                            openai_response.choices[0].message.content = None
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse function call JSON: {match}")
                
                # If we couldn't find a standard JSON format, try a more lenient approach to extract function calls
                if not openai_response.choices[0].message.tool_calls:
                    # Try to find patterns like 'function_name({"param": "value"})'
                    function_pattern = r'(\w+)\s*\(\s*(\{.*?\})\s*\)'
                    matches = re.findall(function_pattern, generated_text, re.DOTALL)
                    
                    if matches:
                        for idx, (function_name, args_str) in enumerate(matches):
                            try:
                                # Try to parse the arguments as JSON
                                arguments = json.loads(args_str)
                                
                                # Create a tool call object
                                tool_call = type('ToolCall', (), {})()
                                tool_call.id = f"call_{idx}"
                                tool_call.type = "function"
                                tool_call.function = type('Function', (), {})()
                                tool_call.function.name = function_name
                                tool_call.function.arguments = json.dumps(arguments)
                                
                                # Add the tool call to the message
                                openai_response.choices[0].message.tool_calls.append(tool_call)
                                
                                # If we found function calls, set content to None as per OpenAI's behavior
                                openai_response.choices[0].message.content = None
                            except json.JSONDecodeError:
                                logger.warning(f"Failed to parse function arguments: {args_str}")
            except Exception as e:
                logger.warning(f"Failed to parse function calls: {e}")
        
        return openai_response


class HuggingFaceCompletions:
    """A wrapper class to mimic OpenAI's completions structure."""
    
    def __init__(self, chat_completions):
        self.create = chat_completions.create


class HuggingFaceChat:
    """A wrapper class to mimic OpenAI's chat structure."""
    
    def __init__(self, chat_completions):
        self.completions = HuggingFaceCompletions(chat_completions)


class HuggingFaceClient:
    """A custom client for Hugging Face's Inference API that mimics the OpenAI interface."""
    
    def __init__(self, api_key, base_url):
        self.api_key = api_key
        self.base_url = base_url
        chat_completions = HuggingFaceChatCompletions(api_key, base_url)
        self.chat = HuggingFaceChat(chat_completions)


class LLM:
    _instances: Dict[str, "LLM"] = {}

    def __new__(
        cls, config_name: str = "default", llm_config: Optional[LLMSettings] = None
    ):
        if config_name not in cls._instances:
            instance = super().__new__(cls)
            instance.__init__(config_name, llm_config)
            cls._instances[config_name] = instance
        return cls._instances[config_name]

    def __init__(
        self, config_name: str = "default", llm_config: Optional[LLMSettings] = None
    ):
        if not hasattr(self, "client"):  # Only initialize if not already initialized
            llm_config = llm_config or config.llm
            llm_config = llm_config.get(config_name, llm_config["default"])
            self.model = llm_config.model
            self.max_tokens = llm_config.max_tokens
            self.temperature = llm_config.temperature
            self.api_type = llm_config.api_type
            self.api_key = llm_config.api_key
            self.api_version = llm_config.api_version
            self.base_url = llm_config.base_url
            
            if self.api_type == "azure":
                self.client = AsyncAzureOpenAI(
                    base_url=self.base_url,
                    api_key=self.api_key,
                    api_version=self.api_version,
                )
            elif self.api_type == "hf":
                self.client = HuggingFaceClient(api_key=self.api_key, base_url=self.base_url)
            else:
                self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    @staticmethod
    def format_messages(messages: List[Union[dict, Message]]) -> List[dict]:
        """
        Format messages for LLM by converting them to OpenAI message format.

        Args:
            messages: List of messages that can be either dict or Message objects

        Returns:
            List[dict]: List of formatted messages in OpenAI format

        Raises:
            ValueError: If messages are invalid or missing required fields
            TypeError: If unsupported message types are provided

        Examples:
            >>> msgs = [
            ...     Message.system_message("You are a helpful assistant"),
            ...     {"role": "user", "content": "Hello"},
            ...     Message.user_message("How are you?")
            ... ]
            >>> formatted = LLM.format_messages(msgs)
        """
        formatted_messages = []

        for message in messages:
            if isinstance(message, dict):
                # If message is already a dict, ensure it has required fields
                if "role" not in message:
                    raise ValueError("Message dict must contain 'role' field")
                formatted_messages.append(message)
            elif isinstance(message, Message):
                # If message is a Message object, convert it to dict
                formatted_messages.append(message.to_dict())
            else:
                raise TypeError(f"Unsupported message type: {type(message)}")

        # Validate all messages have required fields
        for msg in formatted_messages:
            if msg["role"] not in ["system", "user", "assistant", "tool"]:
                raise ValueError(f"Invalid role: {msg['role']}")
            if "content" not in msg and "tool_calls" not in msg:
                raise ValueError(
                    "Message must contain either 'content' or 'tool_calls'"
                )

        return formatted_messages

    @retry(
        wait=wait_random_exponential(min=1, max=60),
        stop=stop_after_attempt(6),
    )
    async def ask(
        self,
        messages: List[Union[dict, Message]],
        system_msgs: Optional[List[Union[dict, Message]]] = None,
        stream: bool = True,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Send a prompt to the LLM and get the response.

        Args:
            messages: List of conversation messages
            system_msgs: Optional system messages to prepend
            stream (bool): Whether to stream the response
            temperature (float): Sampling temperature for the response

        Returns:
            str: The generated response

        Raises:
            ValueError: If messages are invalid or response is empty
            OpenAIError: If API call fails after retries
            Exception: For unexpected errors
        """
        try:
            # Format system and user messages
            if system_msgs:
                system_msgs = self.format_messages(system_msgs)
                messages = system_msgs + self.format_messages(messages)
            else:
                messages = self.format_messages(messages)

            if not stream:
                # Non-streaming request
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=temperature or self.temperature,
                    stream=False,
                )
                if not response.choices or not response.choices[0].message.content:
                    raise ValueError("Empty or invalid response from LLM")
                return response.choices[0].message.content

            # Streaming request
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=temperature or self.temperature,
                stream=True,
            )

            collected_messages = []
            async for chunk in response:
                chunk_message = chunk.choices[0].delta.content or ""
                collected_messages.append(chunk_message)
                print(chunk_message, end="", flush=True)

            print()  # Newline after streaming
            full_response = "".join(collected_messages).strip()
            if not full_response:
                raise ValueError("Empty response from streaming LLM")
            return full_response

        except ValueError as ve:
            logger.error(f"Validation error: {ve}")
            raise
        except OpenAIError as oe:
            logger.error(f"OpenAI API error: {oe}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in ask: {e}")
            raise

    @retry(
        wait=wait_random_exponential(min=1, max=60),
        stop=stop_after_attempt(6),
    )
    async def ask_tool(
        self,
        messages: List[Union[dict, Message]],
        system_msgs: Optional[List[Union[dict, Message]]] = None,
        timeout: int = 60,
        tools: Optional[List[dict]] = None,
        tool_choice: Literal["none", "auto", "required"] = "auto",
        temperature: Optional[float] = None,
        **kwargs,
    ):
        """
        Ask LLM using functions/tools and return the response.

        Args:
            messages: List of conversation messages
            system_msgs: Optional system messages to prepend
            timeout: Request timeout in seconds
            tools: List of tools to use
            tool_choice: Tool choice strategy
            temperature: Sampling temperature for the response
            **kwargs: Additional completion arguments

        Returns:
            ChatCompletionMessage: The model's response

        Raises:
            ValueError: If tools, tool_choice, or messages are invalid
            OpenAIError: If API call fails after retries
            Exception: For unexpected errors
        """
        try:
            # Validate tool_choice
            if tool_choice not in ["none", "auto", "required"]:
                raise ValueError(f"Invalid tool_choice: {tool_choice}")

            # Format messages
            if system_msgs:
                system_msgs = self.format_messages(system_msgs)
                messages = system_msgs + self.format_messages(messages)
            else:
                messages = self.format_messages(messages)

            # Validate tools if provided
            if tools:
                for tool in tools:
                    if not isinstance(tool, dict) or "type" not in tool:
                        raise ValueError("Each tool must be a dict with 'type' field")

            # Set up the completion request
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=temperature or self.temperature,
                max_tokens=self.max_tokens,
                tools=tools,
                tool_choice=tool_choice,
                timeout=timeout,
                **kwargs,
            )

            # Check if response is valid
            if not response.choices or not response.choices[0].message:
                print(response)
                raise ValueError("Invalid or empty response from LLM")

            return response.choices[0].message

        except ValueError as ve:
            logger.error(f"Validation error in ask_tool: {ve}")
            raise
        except OpenAIError as oe:
            if isinstance(oe, AuthenticationError):
                logger.error("Authentication failed. Check API key.")
            elif isinstance(oe, RateLimitError):
                logger.error("Rate limit exceeded. Consider increasing retry attempts.")
            elif isinstance(oe, APIError):
                logger.error(f"API error: {oe}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in ask_tool: {e}")
            raise
