import json
import asyncio
from typing import Dict, Any, List
import openai
import anthropic
from ..core.config import settings

class VariableExtractorService:
    def __init__(self):
        self.openai_client = None
        self.anthropic_client = None
        
        if settings.openai_api_key:
            # Support for custom vLLM endpoints or proxy
            if settings.openai_base_url:
                self.openai_client = openai.AsyncOpenAI(
                    api_key=settings.openai_api_key,
                    base_url=settings.openai_base_url,
                    timeout=60.0,
                    max_retries=3
                )
            else:
                # Use OpenAI proxy service running on host
                proxy_url = "http://localhost:8082/v1"
                self.openai_client = openai.AsyncOpenAI(
                    api_key="proxy-key",
                    base_url=proxy_url,
                    timeout=60.0,
                    max_retries=3
                )
        
        if settings.anthropic_api_key:
            self.anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    
    async def extract_variables(self, question: str, answer: str, policy_variables: List[Dict]) -> Dict[str, Any]:
        """Extract variable values from natural language Q&A pairs"""
        
        system_prompt = self._get_variable_extractor_prompt()
        
        # Format policy variables for the prompt
        variables_description = ""
        for var in policy_variables:
            variables_description += f"""
- name: "{var['name']}"
  type: "{var['type']}"
  description: "{var['description']}"
"""
            if var.get('possible_values'):
                variables_description += f"  possible_values: {var['possible_values']}\n"
        
        user_prompt = f"""
        Extract variable values from the following Q&A pair based on the policy variables defined below.

        Policy Variables:
        {variables_description}

        Q&A Pair:
        Question: "{question}"
        Answer: "{answer}"

        Extract the variable values and return them as a JSON object. If a variable cannot be determined from the Q&A, omit it from the result. Only include variables that can be clearly inferred.

        Example output format:
        {{
            "variable_name": "extracted_value",
            "another_variable": 42,
            "boolean_variable": true
        }}
        """
        
        try:
            if settings.default_llm_provider == "openai" and self.openai_client:
                response = await self._generate_with_openai(system_prompt, user_prompt)
            elif settings.default_llm_provider == "anthropic" and self.anthropic_client:
                response = await self._generate_with_anthropic(system_prompt, user_prompt)
            else:
                raise Exception("No LLM provider configured")
            
            # Log the raw response for debugging
            print(f"Raw LLM response: {repr(response)}")
            
            if not response or not response.strip():
                raise Exception("LLM returned empty response")
            
            # Try to extract JSON from response if it contains extra text
            response_text = response.strip()
            
            # Look for JSON in the response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_text = response_text[json_start:json_end]
            else:
                json_text = response_text
            
            # Parse the JSON response
            extracted_variables = json.loads(json_text)
            
            # Validate extracted variables
            validation_errors = await self.validate_extracted_variables(extracted_variables, policy_variables)
            if validation_errors:
                # Log warnings but don't fail - return best effort extraction
                print(f"Variable extraction warnings: {validation_errors}")
            
            return extracted_variables
            
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON from response: {repr(response)}")
            raise Exception(f"Failed to parse variable extraction response: {str(e)}")
        except Exception as e:
            print(f"Variable extraction error: {str(e)}")
            raise Exception(f"Variable extraction failed: {str(e)}")
    
    async def validate_extracted_variables(self, variables: Dict[str, Any], policy_variables: List[Dict]) -> List[str]:
        """Validate extracted variables against policy variable definitions"""
        errors = []
        
        # Create a lookup for policy variables
        policy_var_lookup = {var['name']: var for var in policy_variables}
        
        for var_name, var_value in variables.items():
            if var_name not in policy_var_lookup:
                errors.append(f"Unknown variable: {var_name}")
                continue
            
            policy_var = policy_var_lookup[var_name]
            var_type = policy_var['type']
            
            # Type validation
            if var_type == 'string' and not isinstance(var_value, str):
                errors.append(f"Variable {var_name} should be string, got {type(var_value)}")
            elif var_type == 'number' and not isinstance(var_value, (int, float)):
                errors.append(f"Variable {var_name} should be number, got {type(var_value)}")
            elif var_type == 'boolean' and not isinstance(var_value, bool):
                errors.append(f"Variable {var_name} should be boolean, got {type(var_value)}")
            elif var_type == 'enum':
                possible_values = policy_var.get('possible_values', [])
                if var_value not in possible_values:
                    errors.append(f"Variable {var_name} value '{var_value}' not in possible values: {possible_values}")
        
        return errors
    
    async def _generate_with_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using OpenAI"""
        response = await self.openai_client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.1,  # Lower temperature for more consistent extraction
            max_tokens=1000
        )
        return response.choices[0].message.content
    
    async def _generate_with_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using Anthropic Claude"""
        response = await self.anthropic_client.messages.create(
            model=settings.anthropic_model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.1,  # Lower temperature for more consistent extraction
            max_tokens=1000
        )
        return response.content[0].text
    
    def _get_variable_extractor_prompt(self) -> str:
        """Get the system prompt for variable extraction"""
        return """
You are a Variable Extractor Agent. Your job is to analyze question-answer pairs and extract specific variable values based on policy variable definitions.

## Core Responsibilities
1. **Parse Natural Language**: Understand the meaning and context in Q&A pairs
2. **Extract Values**: Identify and extract specific variable values mentioned or implied
3. **Type Conversion**: Convert extracted values to the correct data types
4. **Precision**: Only extract variables that are clearly determinable from the text

## Extraction Guidelines

### 1. Be Conservative
- Only extract variables that are clearly mentioned or strongly implied
- When in doubt, omit the variable rather than guess
- Don't make assumptions about missing information

### 2. Handle Different Phrasings
- Look for synonyms and alternative expressions
- Consider context clues and implicit information
- Handle casual language and colloquialisms

### 3. Type Handling
- **Numbers**: Extract numeric values (integers or floats)
- **Strings**: Extract text values, normalize when appropriate
- **Booleans**: Convert yes/no, true/false, positive/negative statements
- **Enums**: Match to closest valid enum value
- **Dates**: Convert date expressions to appropriate format

### 4. Common Patterns
- **Time expressions**: "next week", "in 3 days", "two weeks notice"
- **Quantities**: "5 days", "more than 10", "at least 2 weeks"
- **Approvals**: "manager approved", "got permission", "authorized by"
- **Types/Categories**: Match text to enum categories

## Output Format
Return only valid JSON with extracted variables:
```json
{
    "variable_name": "extracted_value",
    "numeric_variable": 42,
    "boolean_variable": true
}
```

## Examples

**Variables:**
- advance_notice_days (number): Days between request and start date
- request_type (enum): ["vacation", "sick_leave", "emergency"] 
- has_approval (boolean): Whether request is approved

**Q&A:**
Question: "Can I take vacation next week?"
Answer: "Yes, but you need to submit the request now since it's only 5 days notice."

**Extraction:**
```json
{
    "advance_notice_days": 5,
    "request_type": "vacation"
}
```

Note: `has_approval` is not included because it's not clearly determinable from this Q&A.
""" 