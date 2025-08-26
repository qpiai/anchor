import json
from typing import Dict, Any, List
import openai
import anthropic
from ..core.config import settings

class ClarifyingQuestionService:
    def __init__(self):
        self.openai_client = None
        self.anthropic_client = None
        
        if settings.openai_api_key:
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
    
    async def generate_clarifying_questions(self, 
                                          policy_dict: Dict[str, Any], 
                                          extracted_variables: Dict[str, Any],
                                          verification_context: Dict[str, Any]) -> List[str]:
        """Generate intelligent clarifying questions using LLM when verification needs more information"""
        
        system_prompt = self._get_clarifying_questions_prompt()
        
        # Prepare policy context
        policy_context = self._format_policy_context(policy_dict)
        
        user_prompt = f"""
        Policy Context:
        {policy_context}
        
        Current Situation:
        - Extracted Variables: {json.dumps(extracted_variables, indent=2)}
        - Verification Result: {verification_context.get('result', 'needs_clarification')}
        - Issue: {verification_context.get('issue', 'Insufficient information to determine policy compliance')}
        
        Original Q&A:
        Question: "{verification_context.get('question', 'N/A')}"
        Answer: "{verification_context.get('answer', 'N/A')}"
        
        Generate 2-3 specific, helpful questions that would provide the missing information needed to properly evaluate this scenario against the policy. Focus on the most critical missing variables or unclear aspects.
        
        Return your response as a JSON array of questions:
        ["Question 1", "Question 2", "Question 3"]
        """
        
        try:
            if settings.default_llm_provider == "openai" and self.openai_client:
                response = await self._generate_with_openai(system_prompt, user_prompt)
            elif settings.default_llm_provider == "anthropic" and self.anthropic_client:
                response = await self._generate_with_anthropic(system_prompt, user_prompt)
            else:
                # Fallback to rule-based questions
                return self._generate_rule_based_questions(policy_dict, extracted_variables)
            
            # Parse JSON response
            questions = json.loads(response.strip())
            if isinstance(questions, list):
                return questions[:3]  # Limit to 3 questions
            else:
                return self._generate_rule_based_questions(policy_dict, extracted_variables)
                
        except Exception as e:
            print(f"Error generating clarifying questions: {str(e)}")
            return self._generate_rule_based_questions(policy_dict, extracted_variables)
    
    def _format_policy_context(self, policy_dict: Dict[str, Any]) -> str:
        """Format policy information for LLM context"""
        context = f"Policy: {policy_dict.get('policy_name', policy_dict.get('name', 'Unknown Policy'))}\n"
        context += f"Domain: {policy_dict.get('domain', 'general')}\n"
        context += f"Description: {policy_dict.get('description', 'No description available')}\n\n"
        
        # Variables
        if policy_dict.get('variables'):
            context += "Required Variables:\n"
            for var in policy_dict['variables']:
                context += f"- {var['name']} ({var['type']}): {var['description']}\n"
                if var.get('possible_values'):
                    context += f"  Possible values: {var['possible_values']}\n"
        
        # Rules summary
        if policy_dict.get('rules'):
            context += "\nPolicy Rules Summary:\n"
            for i, rule in enumerate(policy_dict['rules'][:5]):  # Limit to first 5 rules
                context += f"- {rule['id']}: {rule['description']}\n"
        
        return context
    
    def _generate_rule_based_questions(self, policy_dict: Dict[str, Any], extracted_variables: Dict[str, Any]) -> List[str]:
        """Fallback rule-based question generation"""
        questions = []
        
        # Find missing critical variables
        if policy_dict.get('variables'):
            for var in policy_dict['variables']:
                var_name = var['name']
                if var_name not in extracted_variables:
                    question = self._generate_variable_question(var)
                    if question:
                        questions.append(question)
                        if len(questions) >= 3:
                            break
        
        # Generic fallbacks if no specific questions
        if not questions:
            domain = policy_dict.get('domain', 'general')
            questions = [
                f"What specific details about this {domain} scenario would help evaluate policy compliance?",
                f"Are there any special circumstances or exceptions that might apply?",
                f"What additional context is needed to make a proper determination?"
            ]
        
        return questions[:3]
    
    def _generate_variable_question(self, var_info: Dict[str, Any]) -> str:
        """Generate a question for a missing variable"""
        var_name = var_info['name']
        var_type = var_info['type']
        description = var_info.get('description', '')
        
        # Create human-readable variable name
        readable_name = var_name.replace('_', ' ').title()
        
        if var_type == 'boolean':
            return f"Is {readable_name} applicable in this case? ({description})"
        elif var_type == 'enum' and var_info.get('possible_values'):
            values = ', '.join(var_info['possible_values'])
            return f"What is the {readable_name}? Options: {values}"
        elif var_type in ['number', 'integer']:
            return f"What is the specific {readable_name} value? ({description})"
        else:
            return f"Could you specify the {readable_name}? ({description})"
    
    async def process_clarifying_response(self, 
                                        original_question: str,
                                        original_answer: str, 
                                        clarifying_qa_pairs: List[Dict[str, str]],
                                        policy_variables: List[Dict]) -> Dict[str, Any]:
        """Process responses to clarifying questions and re-extract variables"""
        
        # Combine all information into a comprehensive context
        combined_context = f"Original Question: {original_question}\n"
        combined_context += f"Original Answer: {original_answer}\n\n"
        
        combined_context += "Additional Information:\n"
        for i, qa in enumerate(clarifying_qa_pairs):
            combined_context += f"Q{i+1}: {qa['question']}\n"
            combined_context += f"A{i+1}: {qa['answer']}\n"
        
        # Re-run variable extraction with the enhanced context
        system_prompt = """
You are a Variable Extractor Agent. Extract specific variable values from the comprehensive context provided, including both original and additional clarifying information.

Focus on extracting accurate values based on all the information provided. Use the clarifying information to resolve any ambiguities from the original context.
"""
        
        # Format variables for extraction
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
        Policy Variables:
        {variables_description}

        Complete Context:
        {combined_context}

        Based on ALL the information above (original Q&A plus clarifying information), extract the variable values and return them as a JSON object:
        
        {{
            "variable_name": "extracted_value",
            "numeric_variable": 42,
            "boolean_variable": true
        }}
        """
        
        try:
            if settings.default_llm_provider == "openai" and self.openai_client:
                response = await self._generate_with_openai(system_prompt, user_prompt)
            elif settings.default_llm_provider == "anthropic" and self.anthropic_client:
                response = await self._generate_with_anthropic(system_prompt, user_prompt)
            else:
                return {}
            
            # Extract JSON from response
            response_text = response.strip()
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_text = response_text[json_start:json_end]
                return json.loads(json_text)
            else:
                return json.loads(response_text)
                
        except Exception as e:
            print(f"Error processing clarifying response: {str(e)}")
            return {}
    
    async def _generate_with_openai(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using OpenAI"""
        response = await self.openai_client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        return response.choices[0].message.content
    
    async def _generate_with_anthropic(self, system_prompt: str, user_prompt: str) -> str:
        """Generate response using Anthropic Claude"""
        response = await self.anthropic_client.messages.create(
            model=settings.anthropic_model,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.3,
            max_tokens=1000
        )
        return response.content[0].text
    
    def _get_clarifying_questions_prompt(self) -> str:
        """System prompt for generating clarifying questions"""
        return """
You are a Policy Clarification Agent. Your job is to generate specific, helpful questions when there isn't enough information to properly evaluate a scenario against a policy.

## Your Task
Analyze the policy, extracted variables, and verification context to identify what critical information is missing. Then generate 2-3 targeted questions that would provide the missing information.

## Guidelines
1. **Be Specific**: Ask for concrete details rather than vague information
2. **Be Policy-Focused**: Questions should relate directly to the policy variables and rules
3. **Be Helpful**: Frame questions in a way that guides the user toward providing useful information
4. **Be Concise**: Keep questions clear and easy to understand
5. **Be Domain-Agnostic**: Work with any type of policy (HR, finance, legal, etc.)

## Question Types to Consider
- Missing variable values that are critical for evaluation
- Clarification of ambiguous statements in the original Q&A
- Additional context that would help apply policy rules correctly
- Verification of assumptions made during variable extraction

## Output Format
Return exactly 2-3 questions as a JSON array. Each question should be a complete, standalone question that the user can answer directly.

## Examples
["What is the employee's current employment status (full-time, part-time, contractor)?", "How many days of advance notice were provided for this request?", "Does this request have manager approval?"]
"""