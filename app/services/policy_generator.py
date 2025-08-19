import yaml
import asyncio
from typing import Dict, Any, List
import openai
import anthropic
from ..core.config import settings

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
                    timeout=60.0,
                    max_retries=3
                )
                print(f"PolicyGeneratorService: Using custom endpoint - {settings.openai_base_url}")
            else:
                # Use OpenAI proxy service running on host
                proxy_url = "http://localhost:8082/v1"
                self.openai_client = openai.AsyncOpenAI(
                    api_key="proxy-key",  # Dummy key for proxy
                    base_url=proxy_url,
                    timeout=60.0,
                    max_retries=3
                )
                print(f"PolicyGeneratorService: Using OpenAI proxy - {proxy_url}")
            print(f"PolicyGeneratorService: OpenAI client configured (base_url={settings.openai_base_url or 'proxy'}, model={settings.openai_model})")
        
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
        1. Output ONLY valid YAML starting with "policy_name:" - no explanations, no markdown blocks
        2. ALL rule conditions MUST use EXACT variable names with comparison operators
        3. FORBIDDEN: "employee is eligible", "user can", "person may" - these are INVALID
        4. REQUIRED FORMAT: variable_name == "value" AND other_var >= 5
        5. ONLY USE THESE OPERATORS: ==, !=, <, >, <=, >=, AND, OR, NOT
        6. STRING VALUES MUST BE IN QUOTES: employee_type == "permanent"
        7. NUMBERS WITHOUT QUOTES: tenure_months >= 12
        8. CONCLUSIONS must be simple text descriptions, NOT variable assignments
        
        EXAMPLE GOOD CONDITIONS:
        - employee_type == "permanent" AND tenure_months >= 6
        - leave_type == "vacation" AND requested_days <= 10
        - is_manager == true OR department == "HR"
        
        EXAMPLE GOOD CONCLUSIONS:
        - "Employee is eligible for leave"
        - "Request is approved"
        - "Additional approval required"
        
        EXAMPLE BAD CONDITIONS (NEVER USE):
        - employee is eligible for leave
        - user can take vacation
        - person may request time off
        
        EXAMPLE BAD CONCLUSIONS (NEVER USE):
        - eligible_for_leave == true
        - status = "approved"
        - result := valid

        
        CRITICAL_YAML_FORMAT:
        ## CRITICAL: YAML Formatting Rules

        Follow this EXACT indentation pattern:

        ```yaml
        policy_name: "name_here"
        domain: "domain_here"
        version: "1.0"
        description: "description here"

        variables:
        - name: "variable_name"
            type: "string"
            description: "description here"
            possible_values: ["val1", "val2"]  # only for enums
        - name: "another_variable"
            type: "number"
            description: "description here"

        rules:
        - id: "rule_001"
            description: "rule description"
            condition: "variable_name == 'value'"
            conclusion: "valid"
            priority: 1
        - id: "rule_002"
            description: "another rule"
            condition: "variable_name != 'value'"
            conclusion: "invalid"
            priority: 2

        constraints:
        - "variable_name != ''"
        - "other_variable > 0"

        examples:
        - question: "example question"
            variables:
            variable_name: "value"
            other_variable: 42
            expected_result: "valid"
            explanation: "explanation here"
        ```

        INDENTATION RULES:
        - Top level: NO indentation
        - List items (-): 2 spaces
        - Properties under list items: 4 spaces
        - Use spaces, NEVER tabs

                """
        
        try:
            if settings.default_llm_provider == "openai" and self.openai_client:
                response = await self._generate_with_openai(system_prompt, user_prompt)
            elif settings.default_llm_provider == "anthropic" and self.anthropic_client:
                response = await self._generate_with_anthropic(system_prompt, user_prompt)
            else:
                raise Exception("No LLM provider configured")
            
            # Extract and parse the YAML response
            yaml_content = self._extract_yaml_from_response(response)
            policy_dict = yaml.safe_load(yaml_content)
            
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
        Return only the new examples in YAML format under an 'examples' key.
        """
        
        user_prompt = f"""
        Here is the existing policy:
        
        {yaml.dump(policy, default_flow_style=False)}
        
        Generate additional test examples that cover edge cases and different scenarios.
        """
        
        try:
            if settings.default_llm_provider == "openai" and self.openai_client:
                response = await self._generate_with_openai(system_prompt, user_prompt)
            else:
                response = await self._generate_with_anthropic(system_prompt, user_prompt)
            
            new_examples = yaml.safe_load(response)
            
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
        response = await self.openai_client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=4000
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
    

    def _simple_yaml_fix(self, yaml_content: str) -> str:
        """Simple fallback YAML fix"""
        lines = yaml_content.split('\n')
        fixed = []
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                fixed.append('')
            elif stripped.startswith('policy_name:') or stripped.startswith('domain:') or stripped.startswith('version:') or stripped.startswith('description:'):
                fixed.append(stripped)
            elif stripped.endswith(':') and stripped in ['variables:', 'rules:', 'constraints:', 'examples:']:
                fixed.append(stripped)
            elif stripped.startswith('- '):
                fixed.append('  ' + stripped)
            elif ':' in stripped:
                fixed.append('    ' + stripped)
            else:
                fixed.append(line)
        
        return '\n'.join(fixed)


    def _fix_yaml_indentation(self, yaml_content: str) -> str:
        """Fix YAML indentation issues"""
        lines = yaml_content.split('\n')
        fixed_lines = []
        current_section = None
        
        for line in lines:
            stripped = line.strip()
            
            if not stripped:
                fixed_lines.append('')
                continue
            
            # Top-level keys
            if stripped.endswith(':') and not stripped.startswith('-'):
                if stripped.split(':')[0] in ['policy_name', 'domain', 'version', 'description', 'variables', 'rules', 'constraints', 'examples']:
                    current_section = stripped.split(':')[0]
                    fixed_lines.append(stripped)
                    continue
            
            # Handle other top-level properties
            if ':' in stripped and not stripped.startswith('-') and current_section in [None, 'policy_name', 'domain', 'version', 'description']:
                fixed_lines.append(stripped)
                continue
            
            # List items (variables, rules, examples, constraints)
            if stripped.startswith('- '):
                if current_section in ['variables', 'rules', 'examples']:
                    fixed_lines.append('  ' + stripped)  # 2 spaces
                else:  # constraints
                    fixed_lines.append('  ' + stripped)
                continue
            
            # Properties under list items
            if ':' in stripped and current_section in ['variables', 'rules', 'examples']:
                fixed_lines.append('    ' + stripped)  # 4 spaces
                continue
            
            # Special handling for examples variables section
            if current_section == 'examples' and not stripped.startswith('-') and not ':' in stripped:
                fixed_lines.append('      ' + stripped)  # 6 spaces for nested content
                continue
            
            # Default: preserve line as-is if it already has proper indentation
            if line.startswith('  '):
                fixed_lines.append(line)
            else:
                fixed_lines.append('  ' + stripped)
        
        result = '\n'.join(fixed_lines)
        
        # Validate the fixed YAML
        try:
            import yaml
            yaml.safe_load(result)
            print(f"PolicyGeneratorService: Fixed YAML successfully validated")
            return result
        except yaml.YAMLError as e:
            print(f"PolicyGeneratorService: YAML fix failed, using simple fallback: {e}")
            return self._simple_yaml_fix(yaml_content)

    def _extract_yaml_from_response(self, response: str) -> str:
        """Extract and fix YAML content from LLM response"""
        import re
        
        # Remove <think> tags
        response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
        
        # Try markdown code blocks first
        yaml_pattern = r'```(?:yaml|yml)?\s*\n(.*?)\n```'
        matches = re.findall(yaml_pattern, response, re.DOTALL | re.IGNORECASE)
        
        if matches:
            yaml_content = matches[0].strip()
            return self._fix_yaml_indentation(yaml_content)
        
        # Extract YAML structure
        lines = response.split('\n')
        yaml_lines = []
        in_yaml = False
        
        for line in lines:
            if line.strip().startswith(('policy_name:', 'domain:', 'version:')):
                in_yaml = True
            if in_yaml:
                yaml_lines.append(line)
        
        if yaml_lines:
            yaml_content = '\n'.join(yaml_lines).strip()
            return self._fix_yaml_indentation(yaml_content)
        
        return response.strip()

    def _get_policy_generator_prompt(self) -> str:
        """Get the system prompt for policy generation"""
        return """
    You are a specialized Policy Generator Agent responsible for converting organizational documents, procedures, and requirements into structured, machine-verifiable policies.

    ## CRITICAL: Output Format Requirements
    - **ONLY output valid YAML**
    - **NO explanatory text before or after the YAML**
    - **NO markdown code blocks** 
    - **Start directly with policy_name:**

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

    ### Two Approaches for Rules:

    #### Approach 1: Positive Conditions (Recommended)
    Write conditions that describe VALID scenarios:
    ```yaml
    - id: "vacation_approval"
    condition: "employee_type == 'permanent' AND advance_notice_days >= 14"
    conclusion: "valid"
    description: "Permanent employees can take vacation with 2+ weeks notice"
    ```

    #### Approach 2: Negative Conditions  
    Write conditions that describe INVALID scenarios:
    ```yaml
    - id: "insufficient_notice"
    condition: "employee_type == 'permanent' AND advance_notice_days < 14"
    conclusion: "invalid" 
    description: "Permanent employees need 2+ weeks notice"
    ```

    ## Required YAML Structure
    ```yaml
    policy_name: "descriptive_name"
    domain: "hr|legal|finance|operations"
    version: "1.0"
    description: "Brief description of policy purpose"

    variables:
    - name: "variable_name"
        type: "string|number|boolean|date|enum"
        description: "Clear description for LLM extraction"
        possible_values: ["value1", "value2"]  # for enums only
        
    rules:
    - id: "rule_001"
        description: "Human-readable rule description"
        condition: "variable_name == 'value' AND other_variable > 5"
        conclusion: "valid"  # or "invalid"
        priority: 1-10
        
    constraints:
    - "variable_name > 0"  # Global constraints that always apply
    
    examples:
    - question: "Can I take 5 days vacation next month?"
        variables: {"employee_type": "permanent", "advance_notice_days": 30}
        expected_result: "valid"
        explanation: "Permanent employee with sufficient notice"
    ```

    ## Variable Best Practices
    - **Use enums** for categorical data with known values
    - **Add approval variables** like "has_manager_approval" for workflow rules
    - **Include sufficient context** in descriptions for extraction
    - **Use boolean flags** for yes/no decisions

    ## Rule Writing Patterns

    ### Pattern 1: Approval Requirements
    ```yaml
    - id: "manager_approval_required"
    condition: "amount > 1000 AND has_manager_approval == true"
    conclusion: "valid"
    ```

    ### Pattern 2: Eligibility Rules  
    ```yaml
    - id: "employee_eligibility"
    condition: "employee_type == 'contractor'"
    conclusion: "invalid"
    ```

    ### Pattern 3: Time-based Rules
    ```yaml
    - id: "advance_notice"
    condition: "notice_days >= 14 AND request_type == 'vacation'"
    conclusion: "valid"
    ```

    ### Pattern 4: Hierarchical Approval
    ```yaml
    - id: "ceo_approval_large"
    condition: "amount > 100000 AND has_ceo_approval == true"
    conclusion: "valid"
    ```

    Remember: Each rule should be atomic and test one specific aspect of the policy.
    """