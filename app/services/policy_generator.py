import json
import asyncio
from typing import Dict, Any, List
import openai
import anthropic
from ..core.config import settings, get_openai_api_params

class PolicyGeneratorService:
    def __init__(self):
        self.openai_client = None
        self.anthropic_client = None
        
        if settings.openai_api_key:
            # Support for custom vLLM endpoints or proxy
            if settings.openai_base_url:
                # Use custom endpoint (vLLM or other)
                self.openai_client = openai.AsyncOpenAI(
                    api_key=settings.openai_api_key,
                    base_url=settings.openai_base_url,
                    timeout=180.0,
                    max_retries=2
                )
                print(f"PolicyGeneratorService: Using custom endpoint - {settings.openai_base_url}")
            else:
                # Use direct OpenAI API (no proxy)
                self.openai_client = openai.AsyncOpenAI(
                    api_key=settings.openai_api_key,
                    timeout=180.0,
                    max_retries=2
                )
                print("PolicyGeneratorService: Using direct OpenAI API")
            print(f"PolicyGeneratorService: OpenAI client configured (base_url={settings.openai_base_url or 'direct'}, model={settings.openai_model})")
        
        if settings.anthropic_api_key:
            self.anthropic_client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    
    async def generate_policy_from_document(self, document_content: str, domain: str) -> Dict[str, Any]:
        """Convert uploaded document into structured policy using LLM"""
        
        system_prompt = self._get_policy_generator_prompt()
        user_prompt = f"""
        Generate a structured policy from the following document.

        Domain: {domain}
        
        Document Content:
        {document_content}
        
        CRITICAL REQUIREMENTS:
        1. Output ONLY valid JSON - no explanations, no markdown blocks, no extra text
        2. ALL rule conditions MUST use EXACT variable names with comparison operators
        3. FORBIDDEN: "employee is eligible", "user can", "person may" - these are INVALID
        4. REQUIRED FORMAT: variable_name == "value" AND other_var >= 5
        5. ONLY USE THESE OPERATORS: ==, !=, <, >, <=, >=, AND, OR, NOT
        6. STRING VALUES MUST BE IN QUOTES: employee_type == "permanent"
        7. NUMBERS WITHOUT QUOTES: tenure_months >= 12
        8. CONCLUSIONS must be simple text descriptions, NOT variable assignments
        9. Use "valid" or "invalid" as conclusions for rule enforcement
        10. ❌ MANDATORY VARIABLES MUST NOT HAVE DEFAULT VALUES - this defeats clarification logic
        
        REQUIRED JSON SCHEMA:
        {{
          "policy_name": "string",
          "domain": "string",
          "version": "1.0", 
          "description": "string",
          "variables": [
            {{
              "name": "variable_name",
              "type": "string|number|boolean|enum",
              "description": "description",
              "possible_values": ["val1", "val2"],
              "is_mandatory": true
            }}
          ],
          "rules": [
            {{
              "id": "rule_id",
              "description": "rule description", 
              "condition": "formal_logical_condition",
              "conclusion": "valid|invalid",
              "priority": 1
            }}
          ],
          "constraints": ["constraint1", "constraint2"],
          "examples": [
            {{
              "question": "example question",
              "variables": {{"var": "value"}},
              "expected_result": "valid|invalid",
              "explanation": "why this result"
            }}
          ]
        }}
        
        EXAMPLE GOOD CONDITIONS:
        - employee_type == "permanent" AND tenure_months >= 6
        - leave_type == "vacation" AND requested_days <= 10
        - is_manager == true OR department == "HR"
        
        EXAMPLE BAD CONDITIONS (NEVER USE):
        - employee is eligible for leave
        - user can take vacation
        - person may request time off
        
        Output ONLY the JSON object. Start with {{ and end with }}.
        """
        
        try:
            if settings.default_llm_provider == "openai" and self.openai_client:
                response = await self._generate_with_openai(system_prompt, user_prompt)
            elif settings.default_llm_provider == "anthropic" and self.anthropic_client:
                response = await self._generate_with_anthropic(system_prompt, user_prompt)
            else:
                raise Exception("No LLM provider configured")
            
            # Extract and parse the JSON response
            json_content = self._extract_json_from_response(response)
            policy_dict = json.loads(json_content)
            
            # Validate the generated policy
            validation_errors = await self.validate_generated_policy(policy_dict)
            if validation_errors:
                raise Exception(f"Policy validation failed: {validation_errors}")
            
            return policy_dict
            
        except Exception as e:
            print(f"PolicyGeneratorService: Policy generation failed: {type(e).__name__}: {str(e)}")
            raise Exception(f"Policy generation failed: {str(e)}")
    
    async def enhance_policy_with_examples(self, policy: Dict) -> Dict:
        """Add more examples to an existing policy"""
        
        system_prompt = """
        You are a Policy Enhancement Agent. Given an existing policy, generate additional
        realistic examples that test edge cases and different scenarios.
        
        Generate 3-5 additional examples in the same format as existing examples.
        Return only the new examples in JSON format under an 'examples' key.
        """
        
        user_prompt = f"""
        Here is the existing policy:
        
        {json.dumps(policy, indent=2)}
        
        Generate additional test examples that cover edge cases and different scenarios.
        Output only JSON in this format:
        {{
          "examples": [
            {{
              "question": "example question",
              "variables": {{"var": "value"}},
              "expected_result": "valid|invalid",
              "explanation": "explanation"
            }}
          ]
        }}
        """
        
        try:
            if settings.default_llm_provider == "openai" and self.openai_client:
                response = await self._generate_with_openai(system_prompt, user_prompt)
            else:
                response = await self._generate_with_anthropic(system_prompt, user_prompt)
            
            json_content = self._extract_json_from_response(response)
            new_examples = json.loads(json_content)
            
            # Merge new examples with existing ones
            if 'examples' in new_examples:
                existing_examples = policy.get('examples', [])
                policy['examples'] = existing_examples + new_examples['examples']
            
            return policy
            
        except Exception as e:
            # Return original policy if enhancement fails
            return policy
    
    async def validate_generated_policy(self, policy: Dict) -> List[str]:
        """Validate the generated policy structure and return errors"""
        errors = []
        
        # Required fields
        required_fields = ['policy_name', 'domain', 'variables', 'rules']
        for field in required_fields:
            if field not in policy:
                errors.append(f"Missing required field: {field}")
        
        # Validate variables
        if 'variables' in policy:
            for var in policy['variables']:
                if not isinstance(var, dict):
                    errors.append("Variables must be dictionaries")
                    continue
                
                required_var_fields = ['name', 'type', 'description']
                for field in required_var_fields:
                    if field not in var:
                        errors.append(f"Variable missing required field: {field}")
                
                # Validate variable type
                valid_types = ['string', 'number', 'boolean', 'date', 'enum']
                if var.get('type') not in valid_types:
                    errors.append(f"Invalid variable type: {var.get('type')}")
                
                # Enum variables must have possible_values
                if var.get('type') == 'enum' and 'possible_values' not in var:
                    errors.append(f"Enum variable {var.get('name')} must have possible_values")
        
        # Validate rules
        if 'rules' in policy:
            for rule in policy['rules']:
                if not isinstance(rule, dict):
                    errors.append("Rules must be dictionaries")
                    continue
                
                required_rule_fields = ['id', 'description', 'condition', 'conclusion']
                for field in required_rule_fields:
                    if field not in rule:
                        errors.append(f"Rule missing required field: {field}")
        
        return errors
    
    async def _generate_with_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using OpenAI"""
        print(f"PolicyGeneratorService: calling OpenAI (base_url={settings.openai_base_url}, model={settings.openai_model})")
        api_params = get_openai_api_params(max_tokens=4000, temperature=0.3)
        response = await self.openai_client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            **api_params
        )
        return response.choices[0].message.content
    
    async def _generate_with_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using Anthropic Claude"""
        response = await self.anthropic_client.messages.create(
            model=settings.anthropic_model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.3,
            max_tokens=4000
        )
        return response.content[0].text
    



    def _extract_json_from_response(self, response: str) -> str:
        """Extract JSON content from LLM response"""
        import re
        
        # Remove <think> tags
        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
        
        # Try markdown code blocks first
        json_pattern = r'```(?:json)?\s*\n(.*?)\n```'
        matches = re.findall(json_pattern, response, re.DOTALL | re.IGNORECASE)
        
        if matches:
            json_content = matches[0].strip()
            print(f"PolicyGeneratorService: Extracted JSON from code block ({len(json_content)} chars)")
            return json_content
        
        # Try to find JSON structure by looking for braces
        start_brace = response.find('{')
        end_brace = response.rfind('}')
        
        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
            json_content = response[start_brace:end_brace+1].strip()
            print(f"PolicyGeneratorService: Extracted JSON from braces ({len(json_content)} chars)")
            return json_content
        
        # Fallback: return original response and let JSON parser handle the error
        print("PolicyGeneratorService: No JSON structure found, using full response")
        return response.strip()

    def _get_policy_generator_prompt(self) -> str:
        """Get the system prompt for policy generation"""
        return """
    You are a specialized Policy Generator Agent responsible for converting organizational documents, procedures, and requirements into structured, machine-verifiable policies.

    ## CRITICAL: Output Format Requirements
    - **ONLY output valid JSON**
    - **NO explanatory text before or after the JSON**
    - **NO markdown code blocks** 
    - **Start directly with { and end with }**

    ## Rule Structure Requirements

    ### Conclusions - ONLY TWO OPTIONS:
    - **"valid"**: Use when the condition describes a valid/allowed scenario
    - **"invalid"**: Use when the condition describes an invalid/forbidden scenario

    ### Condition Logic:
    - **CONDITIONS MUST use variable names with operators**: employee_type == "full_time" AND tenure_years >= 2
    - **NEVER use plain English**: ❌ "Eligible for LoA" ✅ "employee_type == 'permanent' AND employment_duration >= 90"
    - **Supported operators**: ==, !=, <, >, <=, >=, AND, OR, NOT
    - **String values in quotes**: department == "HR" 
    - **Numbers without quotes**: salary > 50000
    - **Boolean values**: is_manager == true

    ## Required JSON Structure
    {
      "policy_name": "descriptive_name",
      "domain": "hr|legal|finance|operations",
      "version": "1.0",
      "description": "Brief description of policy purpose",
      "variables": [
        {
          "name": "variable_name",
          "type": "string|number|boolean|date|enum",
          "description": "Clear description for LLM extraction",
          "possible_values": ["value1", "value2"],
          "is_mandatory": true,
          "default_value": "optional_default"
        }
      ],
      "rules": [
        {
          "id": "rule_001",
          "description": "Human-readable rule description",
          "condition": "variable_name == 'value' AND other_variable > 5",
          "conclusion": "valid",
          "priority": 1
        }
      ],
      "constraints": [
        "variable_name > 0"
      ],
      "examples": [
        {
          "question": "Can I take 5 days vacation next month?",
          "variables": {"employee_type": "permanent", "advance_notice_days": 30},
          "expected_result": "valid",
          "explanation": "Permanent employee with sufficient notice"
        }
      ]
    }

    ## Variable Best Practices
    - **Use enums** for categorical data with known values
    - **Add approval variables** like "has_manager_approval" for workflow rules
    - **Include sufficient context** in descriptions for extraction
    - **Use boolean flags** for yes/no decisions
    
    ## Mandatory vs Optional Variables
    - **is_mandatory: true** - Required for policy evaluation (e.g., employee_id, request_amount)
      ❌ **NEVER give default_value to mandatory variables** - defeats the purpose of being mandatory
      ✅ **Mandatory variables without defaults trigger NEEDS_CLARIFICATION** when missing
    - **is_mandatory: false** - Optional variables that may not always be available
      ✅ **default_value** - Used when optional variables cannot be extracted from text
      ✅ **No default_value** - Rules using this optional variable will be skipped if unknown

    ## Rule Writing Patterns

    ### Pattern 1: Approval Requirements
    {
      "id": "manager_approval_required",
      "condition": "amount > 1000 AND has_manager_approval == true",
      "conclusion": "valid"
    }

    ### Pattern 2: Eligibility Rules  
    {
      "id": "employee_eligibility",
      "condition": "employee_type == 'contractor'",
      "conclusion": "invalid"
    }

    ### Pattern 3: Time-based Rules
    {
      "id": "advance_notice",
      "condition": "notice_days >= 14 AND request_type == 'vacation'",
      "conclusion": "valid"
    }

    Remember: Each rule should be atomic and test one specific aspect of the policy.
    """