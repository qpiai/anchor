from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
import uuid

@dataclass
class ConversationContext:
    """Manages conversational context for policy verification"""
    session_id: str
    policy_id: str
    conversation_history: List[Dict[str, Any]]
    accumulated_variables: Dict[str, Any]
    last_verification_result: Optional[str]
    created_at: datetime
    updated_at: datetime

class ContextManager:
    """Manages conversational context and history for policy verification"""
    
    def __init__(self):
        self.active_sessions: Dict[str, ConversationContext] = {}
    
    def create_session(self, policy_id: str) -> str:
        """Create a new conversation session"""
        session_id = str(uuid.uuid4())
        context = ConversationContext(
            session_id=session_id,
            policy_id=policy_id,
            conversation_history=[],
            accumulated_variables={},
            last_verification_result=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        self.active_sessions[session_id] = context
        return session_id
    
    def add_interaction(self, session_id: str, question: str, answer: str, 
                       extracted_variables: Dict[str, Any], result: str) -> None:
        """Add a new interaction to the conversation"""
        if session_id not in self.active_sessions:
            raise ValueError(f"Session {session_id} not found")
        
        context = self.active_sessions[session_id]
        
        # Add to history
        interaction = {
            "timestamp": datetime.utcnow().isoformat(),
            "question": question,
            "answer": answer,
            "extracted_variables": extracted_variables,
            "result": result
        }
        context.conversation_history.append(interaction)
        
        # Update accumulated variables (new values override old ones)
        context.accumulated_variables.update(extracted_variables)
        context.last_verification_result = result
        context.updated_at = datetime.utcnow()
    
    def get_context(self, session_id: str) -> Optional[ConversationContext]:
        """Get conversation context for a session"""
        return self.active_sessions.get(session_id)
    
    def get_contextual_prompt(self, session_id: str, current_question: str, current_answer: str) -> str:
        """Generate a contextual prompt that includes conversation history"""
        context = self.get_context(session_id)
        if not context or not context.conversation_history:
            return f"Question: {current_question}\nAnswer: {current_answer}"
        
        # Build comprehensive context
        prompt = "Previous conversation context:\n"
        
        for i, interaction in enumerate(context.conversation_history[-3:], 1):  # Last 3 interactions
            prompt += f"Q{i}: {interaction['question']}\n"
            prompt += f"A{i}: {interaction['answer']}\n"
            if interaction['extracted_variables']:
                prompt += f"Variables found: {interaction['extracted_variables']}\n"
            prompt += f"Result: {interaction['result']}\n\n"
        
        prompt += f"Current question: {current_question}\n"
        prompt += f"Current answer: {current_answer}\n\n"
        
        if context.accumulated_variables:
            prompt += f"Previously established variables: {context.accumulated_variables}\n"
        
        return prompt
    
    def get_accumulated_variables(self, session_id: str) -> Dict[str, Any]:
        """Get all accumulated variables from the conversation"""
        context = self.get_context(session_id)
        if not context:
            return {}
        return context.accumulated_variables.copy()
    
    def needs_clarification_history(self, session_id: str) -> List[str]:
        """Get history of what was previously asked for clarification"""
        context = self.get_context(session_id)
        if not context:
            return []
        
        clarification_questions = []
        for interaction in context.conversation_history:
            if interaction['result'] == 'needs_clarification':
                # In a real system, we'd store the clarification questions asked
                clarification_questions.append(interaction['question'])
        
        return clarification_questions
    
    def cleanup_old_sessions(self, max_age_hours: int = 24) -> None:
        """Clean up old conversation sessions"""
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        to_remove = []
        for session_id, context in self.active_sessions.items():
            if context.updated_at < cutoff:
                to_remove.append(session_id)
        
        for session_id in to_remove:
            del self.active_sessions[session_id]

# Enhanced Variable Extraction with Context
class ContextualVariableExtractor:
    """Variable extractor that uses conversation context"""
    
    def __init__(self, base_extractor, context_manager: ContextManager):
        self.base_extractor = base_extractor
        self.context_manager = context_manager
    
    async def extract_with_context(self, session_id: str, question: str, answer: str, 
                                 policy_variables: List[Dict]) -> Dict[str, Any]:
        """Extract variables using conversation context"""
        
        # Get existing context
        accumulated_vars = self.context_manager.get_accumulated_variables(session_id)
        contextual_prompt = self.context_manager.get_contextual_prompt(session_id, question, answer)
        
        # Use contextual prompt for extraction
        extracted_vars = await self.base_extractor.extract_variables(
            contextual_prompt,  # Use full context instead of just current Q&A
            "",  # No separate answer since it's in the contextual prompt
            policy_variables
        )
        
        # Merge with accumulated variables (new values take precedence)
        final_vars = accumulated_vars.copy()
        final_vars.update(extracted_vars)
        
        return final_vars
    
    async def handle_follow_up(self, session_id: str, follow_up_question: str, 
                             follow_up_answer: str, policy_variables: List[Dict]) -> Dict[str, Any]:
        """Handle follow-up questions that build on previous context"""
        
        context = self.context_manager.get_context(session_id)
        if not context:
            # No context, treat as new conversation
            return await self.base_extractor.extract_variables(
                follow_up_question, follow_up_answer, policy_variables
            )
        
        # Build comprehensive context
        full_context = f"""
Previous conversation:
{self.context_manager.get_contextual_prompt(session_id, "", "")}

Follow-up question: {follow_up_question}
Follow-up answer: {follow_up_answer}

Based on ALL the information above (previous conversation + follow-up), what are the complete variable values?
"""
        
        # Extract with full context
        extracted_vars = await self.base_extractor.extract_variables(
            full_context,
            "",
            policy_variables
        )
        
        # Merge with accumulated variables
        accumulated_vars = context.accumulated_variables.copy()
        accumulated_vars.update(extracted_vars)
        
        return accumulated_vars

# Example Usage Enhancement
class ContextualVerificationService:
    """Verification service that understands conversation context"""
    
    def __init__(self, base_verification_service, context_manager: ContextManager):
        self.base_service = base_verification_service
        self.context_manager = context_manager
    
    async def verify_with_context(self, session_id: str, question: str, answer: str,
                                z3_constraints: str, policy_rules: List[Dict]) -> Dict[str, Any]:
        """Verify with conversation context"""
        
        context = self.context_manager.get_context(session_id)
        if context:
            # Use accumulated variables as starting point
            variables = context.accumulated_variables.copy()
        else:
            variables = {}
        
        # Add any new variables from current Q&A
        # (This would integrate with the contextual variable extractor)
        
        # Perform verification
        result = self.base_service.verify_scenario(variables, z3_constraints, policy_rules)
        
        # Update context
        self.context_manager.add_interaction(
            session_id, question, answer, variables, result['result']
        )
        
        return result