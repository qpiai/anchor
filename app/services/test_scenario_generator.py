"""
Test Scenario Generator Service

Automatically generates comprehensive test scenarios for policies covering:
1. Missing mandatory variables -> needs_clarification
2. Valid scenarios (happy path) -> valid  
3. Rule violations -> invalid
4. Edge cases -> various outcomes

Based on policy structure (variables, rules, constraints).
"""

import json
import uuid
import re
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from itertools import combinations

from ..models.schemas import (
    TestScenario, TestScenarioCategory, TestScenarioMetadata, 
    TestScenariosResponse, GenerateTestScenariosRequest,
    VerificationResult
)
from ..core.config import settings
from openai import AsyncOpenAI

class TestScenarioGeneratorService:
    
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url
        )
    
    async def generate_test_scenarios(
        self, 
        policy: Dict[str, Any], 
        request: GenerateTestScenariosRequest
    ) -> TestScenariosResponse:
        """Generate comprehensive test scenarios for a policy"""
        
        scenarios = []
        category_counts = {}
        
        for category in request.include_categories:
            category_scenarios = await self._generate_category_scenarios(
                policy, category, request.max_scenarios_per_category
            )
            scenarios.extend(category_scenarios)
            category_counts[category] = len(category_scenarios)
        
        metadata = TestScenarioMetadata(
            total_scenarios=len(scenarios),
            categories=category_counts,
            generation_time=datetime.utcnow(),
            policy_version=policy.get('version', '1.0')
        )
        
        return TestScenariosResponse(scenarios=scenarios, metadata=metadata)
    
    async def _generate_category_scenarios(
        self, 
        policy: Dict[str, Any], 
        category: TestScenarioCategory,
        max_scenarios: int
    ) -> List[TestScenario]:
        """Generate scenarios for a specific category"""
        
        if category == TestScenarioCategory.MISSING_MANDATORY:
            return await self._generate_missing_mandatory_scenarios(policy, max_scenarios)
        elif category == TestScenarioCategory.VALID_SCENARIOS:
            return await self._generate_valid_scenarios(policy, max_scenarios)
        elif category == TestScenarioCategory.RULE_VIOLATIONS:
            return await self._generate_rule_violation_scenarios(policy, max_scenarios)
        elif category == TestScenarioCategory.EDGE_CASES:
            return await self._generate_edge_case_scenarios(policy, max_scenarios)
        else:
            return []
    
    async def _generate_missing_mandatory_scenarios(
        self, 
        policy: Dict[str, Any], 
        max_scenarios: int
    ) -> List[TestScenario]:
        """Generate scenarios with missing mandatory variables"""
        
        mandatory_vars = self._get_mandatory_variables(policy)
        if not mandatory_vars:
            return []
        
        scenarios = []
        
        # Single missing mandatory variable scenarios
        for var in mandatory_vars[:max_scenarios//2]:
            missing_vars = [var['name']]
            scenario = await self._generate_natural_scenario(
                policy,
                TestScenarioCategory.MISSING_MANDATORY,
                f"Missing {var['name']}",
                missing_variables=missing_vars,
                expected_result=VerificationResult.NEEDS_CLARIFICATION
            )
            scenarios.append(scenario)
        
        # Multiple missing mandatory variables scenario
        if len(mandatory_vars) > 1 and len(scenarios) < max_scenarios:
            multiple_missing = [var['name'] for var in mandatory_vars[:3]]  # Max 3 for clarity
            scenario = await self._generate_natural_scenario(
                policy,
                TestScenarioCategory.MISSING_MANDATORY,
                f"Multiple missing mandatory variables",
                missing_variables=multiple_missing,
                expected_result=VerificationResult.NEEDS_CLARIFICATION
            )
            scenarios.append(scenario)
        
        return scenarios[:max_scenarios]
    
    async def _generate_valid_scenarios(
        self, 
        policy: Dict[str, Any], 
        max_scenarios: int
    ) -> List[TestScenario]:
        """Generate valid scenarios (happy path)"""
        
        scenarios = []
        mandatory_vars = self._get_mandatory_variables(policy)
        optional_vars = self._get_optional_variables(policy)
        
        # Basic valid scenario - all mandatory provided
        scenario = await self._generate_natural_scenario(
            policy,
            TestScenarioCategory.VALID_SCENARIOS,
            "Basic valid scenario",
            include_mandatory=True,
            expected_result=VerificationResult.VALID
        )
        scenarios.append(scenario)
        
        # Valid scenarios with different optional variable combinations
        for i in range(min(max_scenarios - 1, 3)):
            optional_subset = optional_vars[:i+1] if optional_vars else []
            scenario = await self._generate_natural_scenario(
                policy,
                TestScenarioCategory.VALID_SCENARIOS,
                f"Valid with optional variables {i+1}",
                include_mandatory=True,
                include_optional=optional_subset,
                expected_result=VerificationResult.VALID
            )
            scenarios.append(scenario)
        
        return scenarios[:max_scenarios]
    
    async def _generate_rule_violation_scenarios(
        self, 
        policy: Dict[str, Any], 
        max_scenarios: int
    ) -> List[TestScenario]:
        """Generate scenarios that violate specific rules"""
        
        scenarios = []
        rules = policy.get('rules', [])
        invalid_rules = [rule for rule in rules if rule.get('conclusion') == 'invalid']
        
        for rule in invalid_rules[:max_scenarios]:
            # Generate scenario that satisfies this rule's condition to trigger violation
            scenario = await self._generate_rule_violation_scenario(policy, rule)
            scenarios.append(scenario)
        
        return scenarios
    
    async def _generate_edge_case_scenarios(
        self, 
        policy: Dict[str, Any], 
        max_scenarios: int
    ) -> List[TestScenario]:
        """Generate edge case scenarios"""
        
        scenarios = []
        
        # Optional variables without defaults (should skip rules)
        optional_no_defaults = [
            var for var in policy.get('variables', [])
            if not var.get('is_mandatory', True) and not var.get('default_value')
        ]
        
        if optional_no_defaults and len(scenarios) < max_scenarios:
            scenario = await self._generate_natural_scenario(
                policy,
                TestScenarioCategory.EDGE_CASES,
                "Optional without defaults - rule skipping",
                include_mandatory=True,
                expected_result=VerificationResult.VALID,
                description="Tests rule skipping for optional variables without defaults"
            )
            scenarios.append(scenario)
        
        # Boundary value testing for numeric variables
        numeric_vars = [
            var for var in policy.get('variables', [])
            if var.get('type') == 'number'
        ]
        
        for var in numeric_vars[:min(2, max_scenarios - len(scenarios))]:
            scenario = await self._generate_boundary_scenario(policy, var)
            scenarios.append(scenario)
        
        # Enum edge cases
        enum_vars = [
            var for var in policy.get('variables', [])
            if var.get('type') == 'enum' and var.get('possible_values')
        ]
        
        for var in enum_vars[:min(1, max_scenarios - len(scenarios))]:
            scenario = await self._generate_enum_edge_scenario(policy, var)
            scenarios.append(scenario)
        
        return scenarios[:max_scenarios]
    
    async def _generate_natural_scenario(
        self,
        policy: Dict[str, Any],
        category: TestScenarioCategory,
        name: str,
        missing_variables: List[str] = None,
        include_mandatory: bool = False,
        include_optional: List[Dict] = None,
        expected_result: VerificationResult = VerificationResult.VALID,
        description: str = None
    ) -> TestScenario:
        """Generate natural language question/answer using LLM"""
        
        # Create context for LLM
        policy_context = self._build_policy_context(policy)
        
        # Build variable inclusion instructions
        var_instructions = ""
        expected_variables = {}
        
        if include_mandatory:
            mandatory_vars = self._get_mandatory_variables(policy)
            var_instructions += f"Include these mandatory variables with realistic values: {[v['name'] for v in mandatory_vars]}\n"
            for var in mandatory_vars:
                expected_variables[var['name']] = self._generate_realistic_value(var)
        
        if include_optional:
            var_instructions += f"Include these optional variables: {[v['name'] for v in include_optional]}\n"
            for var in include_optional:
                expected_variables[var['name']] = self._generate_realistic_value(var)
        
        if missing_variables:
            var_instructions += f"DO NOT include these variables: {missing_variables}\n"
        
        # Create LLM prompt
        prompt = f"""
Generate a natural conversational Q&A pair for testing a {policy['domain']} policy.

Policy Context:
{policy_context}

Requirements:
- Category: {category.value}
- Scenario: {name}
- {var_instructions}
- Make it realistic for {policy['domain']} domain
- Question should be what a user would ask
- Answer should contain the information naturally

Return JSON format:
{{
    "question": "natural question",
    "answer": "natural answer with the required information"
}}
"""
        
        try:
            response = await self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "You are a JSON generator. Return only valid JSON without any markdown formatting or additional text."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=400,
                response_format={"type": "json_object"}
            )
            
            # Clean response content and parse JSON
            content = response.choices[0].message.content.strip()
            # Remove markdown code blocks if present
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            result = json.loads(content)
            
            return TestScenario(
                id=f"scenario_{uuid.uuid4().hex[:8]}",
                category=category,
                name=name,
                question=result.get('question', 'Can I submit this request?'),
                answer=result.get('answer', 'Yes, I need to submit this request.'),
                expected_result=expected_result,
                expected_missing_variables=missing_variables,
                expected_variables=expected_variables if expected_variables else None,
                description=description or f"Generated {category.value} scenario"
            )
            
        except Exception as e:
            # Fallback to template-based generation
            return self._generate_template_scenario(
                policy, category, name, missing_variables, expected_result, description, include_mandatory
            )
    
    async def _generate_rule_violation_scenario(
        self, 
        policy: Dict[str, Any], 
        rule: Dict[str, Any]
    ) -> TestScenario:
        """Generate scenario that triggers a specific rule violation"""
        
        rule_condition = rule.get('condition', '')
        rule_id = rule.get('id', 'unknown_rule')
        
        # Parse rule condition to understand what values would trigger it
        variable_values = self._parse_rule_condition_for_violation(policy, rule_condition)
        
        # Generate natural scenario with these values
        scenario = await self._generate_natural_scenario(
            policy,
            TestScenarioCategory.RULE_VIOLATIONS,
            f"Violation of {rule_id}",
            include_mandatory=True,
            expected_result=VerificationResult.INVALID,
            description=f"Tests violation of rule: {rule.get('description', rule_id)}"
        )
        
        scenario.expected_violated_rule = rule_id
        scenario.expected_variables = variable_values
        
        return scenario
    
    def _get_mandatory_variables(self, policy: Dict[str, Any]) -> List[Dict]:
        """Extract mandatory variables from policy"""
        variables = policy.get('variables', [])
        return [var for var in variables if var.get('is_mandatory', True)]
    
    def _get_optional_variables(self, policy: Dict[str, Any]) -> List[Dict]:
        """Extract optional variables from policy"""
        variables = policy.get('variables', [])
        return [var for var in variables if not var.get('is_mandatory', True)]
    
    def _build_policy_context(self, policy: Dict[str, Any]) -> str:
        """Build context string describing the policy"""
        context = f"Domain: {policy.get('domain', 'general')}\n"
        context += f"Policy: {policy.get('name', 'Unnamed Policy')}\n"
        context += f"Description: {policy.get('description', 'No description')}\n"
        
        variables = policy.get('variables', [])
        if variables:
            context += "Variables:\n"
            for var in variables:
                mandatory = "mandatory" if var.get('is_mandatory', True) else "optional"
                context += f"  - {var['name']} ({var['type']}, {mandatory}): {var['description']}\n"
        
        return context
    
    def _generate_realistic_value(self, variable: Dict[str, Any]) -> Any:
        """Generate realistic value for a variable based on its type"""
        var_type = variable.get('type', 'string')
        var_name = variable.get('name', '').lower()
        
        if var_type == 'enum' and variable.get('possible_values'):
            return variable['possible_values'][0]  # Use first enum value
        elif var_type == 'number':
            if 'amount' in var_name or 'days' in var_name:
                return 100
            elif 'id' in var_name:
                return 12345
            else:
                return 50
        elif var_type == 'boolean':
            return True
        elif var_type == 'date':
            return "2024-01-15"
        else:  # string
            if 'id' in var_name:
                return "EMP123"
            elif 'name' in var_name:
                return "John Doe"
            else:
                return "sample_value"
    
    def _parse_rule_condition_for_violation(
        self, 
        policy: Dict[str, Any], 
        condition: str
    ) -> Dict[str, Any]:
        """Parse rule condition to determine values that would trigger violation"""
        
        variable_values = {}
        
        # Extract variable references and their required values from condition
        # This is a simplified parser - in production, you'd want a more robust one
        
        # Find patterns like "variable_name == 'value'" or "variable_name > number"
        patterns = [
            r"(\w+)\s*==\s*['\"]([^'\"]+)['\"]",  # string equality
            r"(\w+)\s*==\s*(\w+)",                # variable equality
            r"(\w+)\s*>\s*(\d+)",                 # greater than number
            r"(\w+)\s*<\s*(\d+)",                 # less than number
            r"(\w+)\s*>=\s*(\d+)",                # greater equal number
            r"(\w+)\s*<=\s*(\d+)",                # less equal number
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, condition)
            for match in matches:
                var_name, value = match
                if var_name in [v['name'] for v in policy.get('variables', [])]:
                    # Convert value to appropriate type
                    if value.isdigit():
                        variable_values[var_name] = int(value) + 1  # Trigger condition
                    else:
                        variable_values[var_name] = value
        
        # Add mandatory variables with default values if not specified
        for var in self._get_mandatory_variables(policy):
            if var['name'] not in variable_values:
                variable_values[var['name']] = self._generate_realistic_value(var)
        
        return variable_values
    
    async def _generate_boundary_scenario(
        self, 
        policy: Dict[str, Any], 
        variable: Dict[str, Any]
    ) -> TestScenario:
        """Generate boundary value test scenario"""
        
        return await self._generate_natural_scenario(
            policy,
            TestScenarioCategory.EDGE_CASES,
            f"Boundary test for {variable['name']}",
            include_mandatory=True,
            expected_result=VerificationResult.VALID,
            description=f"Tests boundary values for numeric variable {variable['name']}"
        )
    
    async def _generate_enum_edge_scenario(
        self, 
        policy: Dict[str, Any], 
        variable: Dict[str, Any]
    ) -> TestScenario:
        """Generate enum edge case scenario"""
        
        return await self._generate_natural_scenario(
            policy,
            TestScenarioCategory.EDGE_CASES,
            f"Enum test for {variable['name']}",
            include_mandatory=True,
            expected_result=VerificationResult.VALID,
            description=f"Tests enum values for {variable['name']}: {variable.get('possible_values', [])}"
        )
    
    def _generate_template_scenario(
        self,
        policy: Dict[str, Any],
        category: TestScenarioCategory,
        name: str,
        missing_variables: List[str] = None,
        expected_result: VerificationResult = VerificationResult.VALID,
        description: str = None,
        include_mandatory: bool = False
    ) -> TestScenario:
        """Fallback template-based scenario generation when LLM fails"""
        
        domain = policy.get('domain', 'general')
        mandatory_vars = self._get_mandatory_variables(policy)
        
        # Generate realistic scenarios based on domain and expected result
        if category == TestScenarioCategory.MISSING_MANDATORY:
            if domain == 'hr':
                question = "Can I request time off?"
                answer = "I need to request some leave."
            elif domain == 'compliance':
                question = "Can I access this data?"
                answer = "I need to access some company information."
            else:
                question = "Can you help me with a policy question?"
                answer = "I have a question about policy compliance."
                
        elif category == TestScenarioCategory.VALID_SCENARIOS:
            # For valid scenarios, generate answers that include ALL mandatory variable information
            mandatory_vars = self._get_mandatory_variables(policy)
            if mandatory_vars:
                # Generate dynamic answer based on actual policy variables
                question, answer = self._generate_dynamic_valid_scenario(policy, mandatory_vars)
            else:
                # Fallback for policies without mandatory variables
                if domain == 'hr':
                    question = "Can employee EMP123 take 5 days vacation with 2 weeks notice?"
                    answer = "Employee EMP123 wants 5 days vacation, giving 2 weeks advance notice."
                else:
                    question = "Is this request compliant with policy?"
                    answer = "I have all required approvals and documentation for this request."
        
        else:
            # Default fallback for other categories
            if domain == 'hr':
                question = "Can I request time off?"
                answer = "I need to request some leave."
            elif domain == 'compliance':
                question = "Can I access this data?"
                answer = "I need to access some company information."
            else:
                question = "Can you help me with a policy question?"
                answer = "I have a question about policy compliance."
        
        return TestScenario(
            id=f"scenario_{uuid.uuid4().hex[:8]}",
            category=category,
            name=name,
            question=question,
            answer=answer,
            expected_result=expected_result,
            expected_missing_variables=missing_variables,
            description=description or f"Template-generated {category.value} scenario"
        )
    
    def _generate_dynamic_valid_scenario(self, policy: Dict[str, Any], mandatory_vars: List[Dict]) -> Tuple[str, str]:
        """Generate dynamic question/answer based on actual policy variables"""
        
        domain = policy.get('domain', 'general')
        policy_name = policy.get('name', 'policy')
        
        # Generate question based on domain and policy context
        if domain == 'compliance':
            if 'security' in policy_name.lower() or 'it' in policy_name.lower():
                question = "Can I access company systems and data for my work?"
            else:
                question = "Can I access this data according to policy?"
        elif domain == 'hr':
            question = "Can I submit this request?"
        else:
            question = f"Is my request compliant with the {policy_name}?"
        
        # Build comprehensive answer with all mandatory variables
        answer_parts = []
        
        for var in mandatory_vars:
            var_name = var['name']
            var_type = var['type']
            possible_values = var.get('possible_values', [])
            
            # Generate realistic value and description
            if var_type == 'enum' and possible_values:
                # Use the first valid enum value (usually the "good" option)
                value = possible_values[0]
                answer_parts.append(self._describe_variable_value(var_name, value, var_type))
                
            elif var_type == 'boolean':
                # For boolean variables, choose the value most likely to be valid
                value = self._choose_boolean_value(var_name)
                answer_parts.append(self._describe_variable_value(var_name, value, var_type))
                
            elif var_type == 'number':
                # Generate reasonable numeric values
                value = self._generate_numeric_value(var_name)
                answer_parts.append(self._describe_variable_value(var_name, value, var_type))
                
            elif var_type == 'string':
                # Generate realistic string values
                value = self._generate_string_value(var_name)
                answer_parts.append(self._describe_variable_value(var_name, value, var_type))
            
            else:
                # Fallback for other types
                answer_parts.append(f"The {var_name.replace('_', ' ')} is properly set")
        
        # Combine answer parts into natural language
        if len(answer_parts) <= 2:
            answer = f"{' and '.join(answer_parts)}."
        else:
            answer = f"{', '.join(answer_parts[:-1])}, and {answer_parts[-1]}."
        
        # Add context prefix
        answer = f"Yes, {answer}"
        
        return question, answer
    
    def _describe_variable_value(self, var_name: str, value: Any, var_type: str) -> str:
        """Convert variable name/value into natural language description"""
        
        # Clean variable name for natural language
        readable_name = var_name.replace('_', ' ').replace('has ', '').replace('is ', '')
        
        if var_type == 'boolean':
            if value:
                return f"I have {readable_name}" if 'has_' in var_name else f"I use {readable_name}"
            else:
                return f"I do not have {readable_name}" if 'has_' in var_name else f"I do not use {readable_name}"
        
        elif var_type == 'enum':
            return f"I am using {value.replace('_', ' ')}" if 'type' in var_name else f"my {readable_name} is {value.replace('_', ' ')}"
        
        elif var_type == 'number':
            return f"the {readable_name} is {value}"
        
        else:
            return f"my {readable_name} is {value}"
    
    def _choose_boolean_value(self, var_name: str) -> bool:
        """Choose boolean value most likely to result in valid policy compliance"""
        
        # Variables that should typically be True for compliance
        positive_indicators = [
            'has_authorization', 'has_approval', 'is_approved', 'has_permission',
            'is_encrypted', 'uses_mfa', 'has_authorized_account', 'is_documented',
            'has_explicit_authorization', 'business_need_documented'
        ]
        
        # Variables that should typically be False for compliance  
        negative_indicators = [
            'shares_credentials', 'external_sharing', 'is_public', 'requires_approval'
        ]
        
        var_lower = var_name.lower()
        
        if any(indicator in var_lower for indicator in positive_indicators):
            return True
        elif any(indicator in var_lower for indicator in negative_indicators):
            return False
        else:
            # Default to True (safer for compliance)
            return True
    
    def _generate_numeric_value(self, var_name: str) -> int:
        """Generate realistic numeric value based on variable name"""
        
        if 'days' in var_name or 'notice' in var_name:
            return 14  # 2 weeks notice is common
        elif 'amount' in var_name or 'salary' in var_name:
            return 5000
        elif 'id' in var_name:
            return 12345
        else:
            return 1
    
    def _generate_string_value(self, var_name: str) -> str:
        """Generate realistic string value based on variable name"""
        
        if 'id' in var_name:
            return "EMP12345"
        elif 'name' in var_name:
            return "John Doe"
        elif 'type' in var_name:
            return "standard"
        elif 'department' in var_name:
            return "engineering"
        else:
            return "approved_value"