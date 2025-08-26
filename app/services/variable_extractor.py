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
                # Use direct OpenAI API (no proxy)
                self.openai_client = openai.AsyncOpenAI(
                    api_key=settings.openai_api_key,
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
        Extract variable values from the following Q&A pair, but ONLY for the variables defined in the policy below.

        Policy Variables (THE ONLY VARIABLES YOU CAN EXTRACT):
        {variables_description}

        Q&A Pair:
        Question: "{question}"
        Answer: "{answer}"

        CRITICAL INSTRUCTIONS:
        1. You MUST provide a response for EVERY variable in the Policy Variables list above
        2. Map natural language concepts to these specific defined variables
        3. If the Q&A mentions concepts not covered by the defined variables, ignore them
        4. Use variable descriptions to understand what each variable represents
        5. For enum variables, match to the exact possible_values provided
        6. For boolean variables, interpret yes/no, approval/denial, present/absent
        7. For numeric variables, extract specific numbers mentioned
        8. If a defined variable cannot be determined from the text, set its value to null


        
        Example Mapping Guidelines:
        - "full-time employee" → employee_type: "full_time" (if employee_type is defined)
        - "manager approved" → has_manager_approval: true (if has_manager_approval is defined)
        - "$150 expense" → expense_amount: 150 (if expense_amount is defined)
        - "wearing safety gear" → safety_gear_worn: true (if safety_gear_worn is defined)

        Return a JSON object with ALL defined variables - use null for unknown values.
        {{
            "defined_variable_1": "extracted_value",
            "defined_variable_2": 42,
            "defined_variable_3": null,
            "defined_variable_4": true
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
            
            # Apply default values for missing but inferable variables
            extracted_variables = self._apply_default_values(extracted_variables, policy_variables)
            
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
            
            # Skip validation for special markers
            if var_value in ["MISSING_MANDATORY", "SKIP_RULE"]:
                continue
                
            # Skip validation for null values (they're handled in the processing logic)
            if var_value is None:
                continue
            
            policy_var = policy_var_lookup[var_name]
            var_type = policy_var['type']
            
            # Type validation for actual values only
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
    
    def _apply_default_values(self, extracted_variables: Dict[str, Any], policy_variables: List[Dict]) -> Dict[str, Any]:
        """Return ALL policy variables with comprehensive state handling"""
        result = {}
        
        # Go through every defined policy variable
        for policy_var in policy_variables:
            var_name = policy_var['name']
            is_mandatory = policy_var.get('is_mandatory', True)
            has_default = policy_var.get('default_value') is not None
            
            extracted_value = extracted_variables.get(var_name)
            
            if extracted_value is not None:
                # Case 1: Successfully extracted (not null)
                result[var_name] = extracted_value
            
            elif has_default:
                # Case 2: Not extracted but has default value
                default_value = policy_var['default_value']
                # Convert default based on type
                if policy_var['type'] == 'boolean':
                    result[var_name] = str(default_value).lower() == 'true'
                elif policy_var['type'] == 'number':
                    result[var_name] = float(default_value) if '.' in str(default_value) else int(default_value)
                else:
                    result[var_name] = default_value
            
            elif is_mandatory:
                # Case 3: Mandatory variable not extracted and no default
                # Mark as missing - this will trigger clarifying questions
                result[var_name] = "MISSING_MANDATORY"
            
            else:
                # Case 4: Optional variable not extracted and no default
                # Mark for rule skipping
                result[var_name] = "SKIP_RULE"
        
        return result
    
    
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
You are a Policy-Constrained Variable Extractor Agent. Your job is to extract ONLY the specific variables defined in the policy from natural language question-answer pairs.

## CRITICAL CONSTRAINT
You can ONLY extract variables that are explicitly defined in the policy variable list provided. Do NOT create, infer, or extract any variables beyond what is defined in the policy.

## Core Responsibilities
1. **Policy-First Mapping**: Map natural language concepts to the exact variables defined in the policy
2. **Constrained Extraction**: Extract values for defined variables only, ignore everything else
3. **Type Conversion**: Convert extracted values to match the defined variable types
4. **Conservative Approach**: When unclear, omit the variable rather than guess

## Extraction Strategy

### 1. Policy Variable Mapping
- Study the provided policy variables carefully (name, type, description, possible_values)
- Map natural language concepts to these specific variables
- Use variable descriptions to understand what each variable represents
- If text mentions concepts not covered by defined variables, ignore them

### 2. Natural Language Understanding
- Look for synonyms and different phrasings of the defined variables
- Consider context clues that indicate specific variable values
- Handle casual language and colloquialisms
- Map business terms to formal variable names

### 3. Type Handling
- **Numbers**: Extract numeric values for number-type variables
- **Enums**: Match text to the closest valid option from possible_values
- **Booleans**: Interpret yes/no, positive/negative, present/absent indicators
- **Booleans**: Convert yes/no, true/false, positive/negative statements
- **Enums**: Match to closest valid enum value
- **Dates**: Convert date expressions to appropriate format

### 4. Common Patterns
- **Time expressions**: "next week", "in 3 days", "two weeks notice"
- **Quantities**: "5 days", "more than 10", "at least 2 weeks"
- **Approvals**: "manager approved", "got permission", "authorized by"
- **Types/Categories**: Match text to enum categories
- **Employment types**: "full-time" typically means 40+ hours/week, "part-time" typically means <40 hours/week

### 5. Default Values and Assumptions
When certain variables are not explicitly mentioned but can be reasonably inferred:
- **full_time employees**: Assume hours_per_week = 40 unless stated otherwise
- **part_time employees**: Assume hours_per_week = 20 unless stated otherwise
- **contractor employees**: Assume hours_per_week = 30 unless stated otherwise

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