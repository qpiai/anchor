import json
import logging
import asyncio
from typing import Dict, Any, List
import openai
import anthropic
from ..core.config import settings, get_openai_api_params
from .policy_repair import ensure_policy_compiles, ensure_policy_semantics

logger = logging.getLogger(__name__)

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
        9. Use "valid" or "invalid" as conclusions. VALID needs one "valid" rule to apply and no "invalid" rule to apply. Every limit, cap, deadline, or required approval MUST be an "invalid" rule describing the breach; "valid" rules are standalone permissions only
        10. A variable is is_mandatory true ONLY if EVERY decision under the policy depends on it (who, what, how much, how long). Extensions, approvals, procedure details, and other partial-path facts are is_mandatory false with no default_value. Rare exceptional or adverse conditions a requester would mention if they applied (fault, damage, overnight use, repair) are is_mandatory false with default_value "false".
        12. "constraints" hold only single-number ranges such as "leave_days > 0". Business rules go in "rules".
        11. Mandatory variables must not have a default_value.
        
        REQUIRED JSON SCHEMA:
        {{
          "policy_name": "string",
          "domain": "string",
          "version": "1.0", 
          "description": "string",
          "variables": [
            {{
              "name": "employee_type",
              "type": "enum",
              "description": "Who is requesting. Every leave decision depends on this.",
              "possible_values": ["full_time", "contractor"],
              "is_mandatory": true
            }},
            {{
              "name": "has_manager_approval",
              "type": "boolean",
              "description": "Whether an extension beyond the normal limit was approved. Only extension rules use this.",
              "is_mandatory": false
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

            policy_dict, compile_errors = await ensure_policy_compiles(
                policy_dict,
                self._repair_policy,
            )
            leaky: List[str] = []
            if not compile_errors:
                async def repair_semantics(policy: Dict, problems: List[str]) -> Dict:
                    return await self._repair_policy(policy, problems, source=document_content)
                policy_dict, leaky = await ensure_policy_semantics(policy_dict, repair_semantics)
            policy_dict["_compile_errors"] = compile_errors
            policy_dict["_semantic_warnings"] = [
                f"Rule {rule_id} is a permission that never restricts anything; if it is a limit, "
                "rewrite it as an invalid rule." for rule_id in leaky
            ]
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
    
    async def _repair_policy(self, policy: Dict, errors: List[str], source: str | None = None) -> Dict:
        """Ask GPT for a full corrected policy given compiler or semantics errors."""
        system_prompt = (
            "You repair machine-verifiable policy JSON. "
            "Return ONLY the full corrected policy JSON. "
            "Every name used in a rule condition must be declared in variables "
            "with a type (string, number, boolean, date, or enum), a description, "
            "and possible_values when the type is enum or the values are closed. "
            "Alternatively drop the rule that references an undeclared name. "
            "Keep the same schema: policy_name, domain, version, description, "
            "variables, rules, constraints, examples. "
            "Keep is_mandatory true only for variables every decision depends on. "
            "Extensions, approvals, and procedure details stay is_mandatory false with no default_value."
        )
        user_prompt = (
            "The policy has problems.\n\n"
            f"Problems:\n{json.dumps(errors)}\n\n"
            + (f"Source document:\n{source}\n\n" if source else "")
            + f"Policy:\n{json.dumps(policy)}\n\n"
            "Return the full corrected policy JSON."
        )
        logger.info("Asking the model to repair policy compile errors: %s", errors)
        if settings.default_llm_provider == "openai" and self.openai_client:
            response = await self._generate_with_openai(system_prompt, user_prompt)
        elif self.anthropic_client:
            response = await self._generate_with_anthropic(system_prompt, user_prompt)
        else:
            raise Exception("No LLM provider configured for policy repair")
        repaired = json.loads(self._extract_json_from_response(response))
        structural = await self.validate_generated_policy(repaired)
        if structural:
            raise Exception(f"Repaired policy failed structural validation: {structural}")
        return repaired

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

    ### Conclusions - ONLY TWO OPTIONS, and how the verifier combines them:
    A request is VALID only when at least one "valid" rule applies AND no "invalid" rule applies.
    "valid" rules are alternatives (OR): each one must be a complete, standalone reason to approve,
    such as basic eligibility ("full-time employees may take leave").
    - **"valid"**: a standalone permission. Never use "valid" for a limit, cap, deadline, or approval
      requirement: a "valid" rule that fails does not block anything, so the limit would be ignored.
    - **"invalid"**: a violation. Write EVERY limit, cap, minimum, deadline, prohibited case, and
      required approval as an "invalid" rule that describes breaking it, e.g.
      "leave_days > 30 AND has_manager_approval != true" -> "invalid".
    Test: if a request fails this rule, must it be refused? Then it is an "invalid" rule.

    ### Condition Logic:
    - **CONDITIONS MUST use variable names with operators**: employee_type == "full_time" AND tenure_years >= 2
    - **NEVER use plain English**. Write employee_type == "permanent" AND employment_duration >= 90, not "Eligible for LoA".
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
          "is_mandatory": true
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
    Set is_mandatory true only when EVERY decision under the policy depends on that variable.
    Core facts are who is asking, what is requested, how much, and how long.
    Most policies have only two to four mandatory variables.
    A missing mandatory variable, with no default_value, triggers NEEDS_CLARIFICATION.

    Set is_mandatory false when the variable matters for only some rules. Then choose its default:
    - No default_value for a fact the decision must ask about when it matters: approvals, identity
      checks, submission method, recipient. If such a fact is unstated and a rule could deny on it,
      the verifier asks for it (a request for 45 days with no word on approval gets a question).
    - The default that means "nothing is wrong" for an exceptional or adverse condition a requester
      would mention if it applied: "false" for fault_or_damage_exists, is_overnight_use, repair_performed;
      "true" for a positively phrased catch-all such as safety_rules_compliant. Without a default,
      every ordinary request would be asked about every rare exception.
    Examples with no default: has_manager_approval, submission_method, recipient_department.
    Examples with default "false": fault_or_damage_exists, is_overnight_use, repair_performed.

    ## Constraints
    Use "constraints" ONLY for the range of a single number, e.g. "leave_days > 0",
    "consecutive_use_hours <= 24". Never put a business rule in constraints: a limit, an approval,
    an allowed method, or anything that relates two variables belongs in "rules" as an "invalid" rule.

    Before output, check each variable. If any complete decision does not use it, it is optional.

    ## Rule Writing Patterns

    ### Pattern 1: Approval requirement (a deny rule, never a permit)
    {
      "id": "manager_approval_required",
      "condition": "amount > 1000 AND has_manager_approval != true",
      "conclusion": "invalid"
    }

    ### Pattern 2: Eligibility (one permit for who qualifies, one deny for who does not)
    {
      "id": "eligible_employees",
      "condition": "employee_type == 'full_time'",
      "conclusion": "valid"
    }
    {
      "id": "ineligible_contractors",
      "condition": "employee_type == 'contractor'",
      "conclusion": "invalid"
    }

    ### Pattern 3: Limit with an exception (deny the breach unless the exception holds)
    {
      "id": "max_duration",
      "condition": "leave_days > 30 AND has_manager_approval != true",
      "conclusion": "invalid"
    }

    ### Pattern 4: Deadline
    {
      "id": "advance_notice",
      "condition": "request_type == 'vacation' AND notice_days < 14",
      "conclusion": "invalid"
    }

    ### Coverage
    Every requirement in the document that decides approval must appear as a rule. If a requirement
    needs a fact (for example who approved a large contract), declare a variable for it rather than
    dropping the requirement. Do not turn routing text ("approved by the Head of Legal") into a
    permission on its own.

    Remember: Each rule should be atomic and test one specific aspect of the policy.
    """