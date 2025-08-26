import streamlit as st
import requests
import json
import yaml
from typing import Dict, Any
import uuid

# Configuration
API_BASE_URL = "http://localhost:9066"
API_V1_PREFIX = "/api/v1"

st.set_page_config(
    page_title="Automated Reasoning Backend - Test UI",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

def main():
    st.title("🧠 Automated Reasoning Backend")
    st.markdown("**Multi-agent AI system for policy verification and automated reasoning**")
    
    # Sidebar navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.selectbox(
        "Choose a page",
        ["🏠 Dashboard", "📄 Document Upload", "📋 Policy Management", "✏️ Policy Editor", "🔧 Compilation", "✅ Verification", "🧪 Test Scenarios", "🗄️ Database Inspector", "💡 Examples"]
    )
    
    if page == "🏠 Dashboard":
        show_dashboard()
    elif page == "📄 Document Upload":
        show_document_upload()
    elif page == "📋 Policy Management":
        show_policy_management()
    elif page == "✏️ Policy Editor":
        show_policy_editor()
    elif page == "🔧 Compilation":
        show_compilation()
    elif page == "✅ Verification":
        show_verification()
    elif page == "🧪 Test Scenarios":
        show_test_scenarios()
    elif page == "🗄️ Database Inspector":
        show_database_inspector()
    elif page == "💡 Examples":
        show_examples()

def show_dashboard():
    st.header("System Dashboard")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Health Check")
        if st.button("Check System Health"):
            try:
                response = requests.get(f"{API_BASE_URL}/health")
                if response.status_code == 200:
                    health_data = response.json()
                    st.success(f"System Status: {health_data['status']}")
                    
                    # Show component status
                    st.write("**Component Status:**")
                    for component, status in health_data['components'].items():
                        if "healthy" in status or "configured" in status:
                            st.success(f"✅ {component}: {status}")
                        elif "degraded" in status or "not configured" in status:
                            st.warning(f"⚠️ {component}: {status}")
                        else:
                            st.error(f"❌ {component}: {status}")
                else:
                    st.error(f"Health check failed: {response.status_code}")
            except Exception as e:
                st.error(f"Failed to connect to backend: {str(e)}")
    
    with col2:
        st.subheader("System Statistics")
        if st.button("Get Statistics"):
            try:
                response = requests.get(f"{API_BASE_URL}/status")
                if response.status_code == 200:
                    stats = response.json()['statistics']
                    
                    st.metric("Total Documents", stats['documents']['total'])
                    st.metric("Total Policies", stats['policies']['total'])
                    st.metric("Successful Compilations", stats['compilations']['successful'])
                    st.metric("Total Verifications", stats['verifications']['total'])
                    
                    # Show breakdowns
                    if stats['documents']['by_domain']:
                        st.write("**Documents by Domain:**")
                        for domain, count in stats['documents']['by_domain'].items():
                            st.write(f"- {domain}: {count}")
                            
                else:
                    st.error("Failed to get statistics")
            except Exception as e:
                st.error(f"Error: {str(e)}")

def show_document_upload():
    st.header("Document Upload")
    
    st.markdown("""
    Upload policy documents (PDF, DOCX, TXT) to automatically generate structured policies.
    The system will extract rules and create formal policy definitions.
    """)
    
    # File upload
    uploaded_file = st.file_uploader(
        "Choose a policy document",
        type=['pdf', 'docx', 'txt'],
        help="Upload a policy document to generate structured policies"
    )
    
    # Domain selection
    domain = st.selectbox(
        "Select policy domain",
        ["hr", "legal", "finance", "operations", "compliance"],
        help="Choose the domain that best fits your policy document"
    )
    
    if uploaded_file is not None and st.button("Upload and Process"):
        with st.spinner("Uploading and processing document..."):
            try:
                files = {"file": uploaded_file}
                data = {"domain": domain}
                
                response = requests.post(
                    f"{API_BASE_URL}{API_V1_PREFIX}/documents/upload",
                    files=files,
                    data=data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    st.success(f"Document uploaded successfully!")
                    st.info(f"Document ID: {result['document_id']}")
                    st.info("Policy generation started in background. Check the Policy Management page in a few moments.")
                    
                    # Store document ID in session state
                    st.session_state.last_document_id = result['document_id']
                    
                else:
                    st.error(f"Upload failed: {response.text}")
                    
            except Exception as e:
                st.error(f"Error uploading document: {str(e)}")

def show_policy_management():
    st.header("Policy Management")
    
    # List existing policies
    st.subheader("Existing Policies")
    
    if st.button("Refresh Policy List"):
        try:
            response = requests.get(f"{API_BASE_URL}{API_V1_PREFIX}/policies/")
            if response.status_code == 200:
                policies = response.json()
                
                if policies:
                    for policy in policies:
                        with st.expander(f"📋 {policy['name']} ({policy['domain']}) - {policy['status']}"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                st.write(f"**ID:** {policy['id']}")
                                st.write(f"**Description:** {policy['description'] or 'No description'}")
                                st.write(f"**Version:** {policy['version']}")
                                st.write(f"**Status:** {policy['status']}")
                            
                            with col2:
                                st.write(f"**Variables:** {len(policy['variables'] or [])}")
                                st.write(f"**Rules:** {len(policy['rules'] or [])}")
                                st.write(f"**Constraints:** {len(policy['constraints'] or [])}")
                                st.write(f"**Created:** {policy['created_at']}")
                            
                            # Action buttons
                            col3, col4, col5 = st.columns(3)
                            
                            with col3:
                                if st.button(f"View Details", key=f"view_{policy['id']}"):
                                    st.session_state.selected_policy_id = policy['id']
                                    
                                if st.button(f"Edit Policy", key=f"edit_{policy['id']}"):
                                    st.session_state.selected_policy_for_editing = policy['id']
                                    st.session_state.redirect_to_editor = True
                            
                            with col4:
                                if policy['status'] == 'draft' and st.button(f"Compile", key=f"compile_{policy['id']}"):
                                    compile_policy(policy['id'])
                                    
                                if st.button(f"Delete", key=f"delete_{policy['id']}", type="secondary"):
                                    if st.session_state.get(f"confirm_delete_{policy['id']}", False):
                                        delete_policy(policy['id'])
                                        st.session_state[f"confirm_delete_{policy['id']}"] = False
                                        st.rerun()
                                    else:
                                        st.session_state[f"confirm_delete_{policy['id']}"] = True
                                        st.warning(f"Click delete again to confirm deletion of {policy['name']}")
                            
                            with col5:
                                if policy['status'] == 'compiled' and st.button(f"Test Verify", key=f"verify_{policy['id']}"):
                                    st.session_state.selected_policy_for_verification = policy['id']
                else:
                    st.info("No policies found. Upload a document to generate policies.")
            else:
                st.error("Failed to fetch policies")
                
        except Exception as e:
            st.error(f"Error: {str(e)}")
    
    # Show policy details if selected
    if 'selected_policy_id' in st.session_state and st.session_state.selected_policy_id:
        st.divider()
        show_policy_details(st.session_state.selected_policy_id)

def show_policy_details(policy_id: str):
    """Show detailed policy information"""
    try:
        response = requests.get(f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}")
        if response.status_code == 200:
            policy = response.json()
            
            st.subheader(f"Policy Details: {policy['name']}")
            
            # Variables
            if policy['variables']:
                st.write("**Variables:**")
                for var in policy['variables']:
                    st.write(f"- {var['name']} ({var['type']}): {var['description']}")
                    if var.get('possible_values'):
                        st.write(f"  Possible values: {var['possible_values']}")
            
            # Rules
            if policy['rules']:
                st.write("**Rules:**")
                for rule in policy['rules']:
                    st.write(f"- **{rule['id']}**: {rule['description']}")
                    st.write(f"  Condition: `{rule['condition']}`")
                    st.write(f"  Conclusion: `{rule['conclusion']}`")
            
            # Constraints
            if policy['constraints']:
                st.write("**Constraints:**")
                for constraint in policy['constraints']:
                    st.write(f"- {constraint}")
                    
    except Exception as e:
        st.error(f"Error fetching policy details: {str(e)}")

def compile_policy(policy_id: str):
    """Compile a policy to Z3 constraints"""
    with st.spinner("Compiling policy..."):
        try:
            response = requests.post(f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/compile")
            if response.status_code == 200:
                result = response.json()
                if result['status'] == 'success':
                    st.success("✅ Policy compiled successfully!")
                else:
                    st.error(f"❌ Compilation failed: {result['errors']}")
            else:
                st.error(f"Compilation request failed: {response.text}")
        except Exception as e:
            st.error(f"Error: {str(e)}")

def show_compilation():
    st.header("Policy Compilation")
    
    st.markdown("""
    Convert policies to formal Z3 logic constraints for mathematical verification.
    Only compiled policies can be used for verification.
    """)
    
    # Get policy ID
    policy_id = st.text_input("Policy ID", help="Enter the UUID of the policy to compile")
    
    if policy_id and st.button("Compile Policy"):
        compile_policy(policy_id)
    
    # Validation
    if policy_id and st.button("Validate Policy Structure"):
        try:
            response = requests.post(f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/validate")
            if response.status_code == 200:
                result = response.json()
                if result['valid']:
                    st.success("✅ Policy structure is valid")
                else:
                    st.error("❌ Policy structure has errors:")
                    for error in result['errors']:
                        st.error(f"- {error}")
            else:
                st.error("Validation failed")
        except Exception as e:
            st.error(f"Error: {str(e)}")

def show_verification():
    st.header("Policy Verification")
    
    st.markdown("""
    Test questions and answers against compiled policies to verify compliance.
    The system will extract variables and perform formal verification.
    """)
    
    # Policy selection
    policy_id = st.text_input("Policy ID", 
                             value=st.session_state.get('selected_policy_for_verification', ''),
                             help="Enter the UUID of a compiled policy")
    
    # Conversation mode toggle
    use_conversation_mode = st.checkbox(
        "Enable Conversation Mode", 
        value=False,
        help="Remember previous interactions and build context over multiple Q&A exchanges"
    )
    
    # Show conversation history if in conversation mode
    if use_conversation_mode and 'conversation_history' in st.session_state and policy_id:
        if st.session_state.conversation_history.get(policy_id):
            st.subheader("📝 Conversation History")
            for i, interaction in enumerate(st.session_state.conversation_history[policy_id][-3:], 1):
                with st.expander(f"Interaction {i}: {interaction['result'].title()}"):
                    st.write(f"**Q:** {interaction['question']}")
                    st.write(f"**A:** {interaction['answer']}")
                    if interaction.get('extracted_variables'):
                        st.write(f"**Variables:** {interaction['extracted_variables']}")
            st.divider()
    
    # Q&A input
    col1, col2 = st.columns(2)
    
    with col1:
        if use_conversation_mode:
            question = st.text_area("Question", 
                                   placeholder="e.g., What about a $200 expense? or Can I also expense travel costs?",
                                   help="Ask a follow-up question or new question. Context from previous interactions will be considered.")
        else:
            question = st.text_area("Question", 
                                   placeholder="e.g., Can I expense a $75 software license?",
                                   help="Enter a natural language question about the policy")
    
    with col2:
        if use_conversation_mode:
            answer = st.text_area("Answer", 
                                 placeholder="e.g., Yes, I have receipts. or It was for a client meeting.",
                                 help="Provide additional details. Previous context will be combined with this response.")
        else:
            answer = st.text_area("Answer", 
                                 placeholder="e.g., Yes, but you need manager approval.",
                                 help="Enter the answer to be verified against the policy")
    
    if policy_id and question and answer:
        col3, col4 = st.columns(2)
        
        with col3:
            if st.button("Test Variable Extraction"):
                test_extraction(policy_id, question, answer)
        
        with col4:
            if st.button("Verify Against Policy"):
                verify_qa(policy_id, question, answer)

def test_extraction(policy_id: str, question: str, answer: str):
    """Test variable extraction without verification"""
    with st.spinner("Extracting variables..."):
        try:
            data = {"question": question, "answer": answer}
            response = requests.post(
                f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/test-extraction",
                json=data
            )
            
            if response.status_code == 200:
                result = response.json()
                
                st.subheader("Extracted Variables")
                if result['extracted_variables']:
                    for var, value in result['extracted_variables'].items():
                        st.write(f"- **{var}**: {value}")
                else:
                    st.info("No variables extracted")
                
                if result['validation_errors']:
                    st.warning("Validation Warnings:")
                    for error in result['validation_errors']:
                        st.warning(f"- {error}")
                        
            else:
                st.error(f"Extraction failed: {response.text}")
                
        except Exception as e:
            st.error(f"Error: {str(e)}")

def update_variable_property(policy_id: str, variable_name: str, property_name: str, property_value):
    """Update a specific property of a policy variable"""
    try:
        data = {
            "variable_name": variable_name,
            property_name: property_value
        }
        response = requests.patch(
            f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/variables/{variable_name}",
            json=data
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Failed to update variable: {str(e)}")
        return False

def add_variable(policy_id: str, name: str, var_type: str, description: str, is_mandatory: bool, default_value: str, possible_values: str):
    """Add a new variable to the policy"""
    try:
        data = {
            "name": name,
            "type": var_type,
            "description": description,
            "is_mandatory": is_mandatory
        }
        
        if default_value.strip():
            data["default_value"] = default_value.strip()
        
        if possible_values.strip():
            data["possible_values"] = [v.strip() for v in possible_values.split(",") if v.strip()]
        
        response = requests.post(
            f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/variables",
            json=data
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Failed to add variable: {str(e)}")
        return False

def delete_variable(policy_id: str, variable_name: str):
    """Delete a variable from the policy"""
    try:
        response = requests.delete(
            f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/variables/{variable_name}"
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Failed to delete variable: {str(e)}")
        return False

def add_rule(policy_id: str, rule_id: str, description: str, condition: str, conclusion: str, priority: int):
    """Add a new rule to the policy"""
    try:
        data = {
            "id": rule_id,
            "description": description,
            "condition": condition,
            "conclusion": conclusion,
            "priority": priority
        }
        
        response = requests.post(
            f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/rules",
            json=data
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Failed to add rule: {str(e)}")
        return False

def update_rule(policy_id: str, rule_id: str, description: str, condition: str, conclusion: str, priority: int):
    """Update a rule in the policy"""
    try:
        data = {
            "description": description,
            "condition": condition,
            "conclusion": conclusion,
            "priority": priority
        }
        
        response = requests.patch(
            f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/rules/{rule_id}",
            json=data
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Failed to update rule: {str(e)}")
        return False

def delete_rule(policy_id: str, rule_id: str):
    """Delete a rule from the policy"""
    try:
        response = requests.delete(
            f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/rules/{rule_id}"
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Failed to delete rule: {str(e)}")
        return False

def add_constraint(policy_id: str, constraint: str):
    """Add a new constraint to the policy"""
    try:
        response = requests.post(
            f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/constraints",
            params={"constraint": constraint}
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Failed to add constraint: {str(e)}")
        return False

def delete_constraint(policy_id: str, constraint: str):
    """Delete a constraint from the policy"""
    try:
        response = requests.delete(
            f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/constraints",
            params={"constraint": constraint}
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Failed to delete constraint: {str(e)}")
        return False

def verify_qa(policy_id: str, question: str, answer: str):
    """Verify Q&A against policy"""
    with st.spinner("Verifying against policy..."):
        try:
            data = {"question": question, "answer": answer}
            response = requests.post(
                f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/verify",
                json=data
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Show result
                if result['result'] == 'valid':
                    st.success("✅ VALID - The scenario complies with the policy")
                elif result['result'] == 'invalid':
                    st.error("❌ INVALID - The scenario violates the policy")
                else:
                    st.warning("⚠️ ERROR - Verification failed")
                
                # Show extracted variables with comprehensive status
                st.subheader("Extracted Variables")
                if result['extracted_variables']:
                    col1, col2, col3 = st.columns(3)
                    
                    extracted_vars = []
                    missing_mandatory = []
                    skipped_vars = []
                    
                    for var, value in result['extracted_variables'].items():
                        if value == "MISSING_MANDATORY":
                            missing_mandatory.append(var)
                        elif value == "SKIP_RULE":
                            skipped_vars.append(var)
                        else:
                            extracted_vars.append((var, value))
                    
                    with col1:
                        st.write("**✅ Extracted:**")
                        if extracted_vars:
                            for var, value in extracted_vars:
                                st.write(f"- **{var}**: {value}")
                        else:
                            st.info("None")
                    
                    with col2:
                        st.write("**❓ Missing Mandatory:**")
                        if missing_mandatory:
                            for var in missing_mandatory:
                                st.write(f"- **{var}**")
                        else:
                            st.info("None")
                    
                    with col3:
                        st.write("**⏭️ Skipped (Optional):**")
                        if skipped_vars:
                            for var in skipped_vars:
                                st.write(f"- **{var}**")
                        else:
                            st.info("None")
                
                # Show explanation
                st.subheader("Explanation")
                st.write(result['explanation'])
                
                # Show suggestions if any
                if result['suggestions']:
                    st.subheader("Suggestions")
                    for suggestion in result['suggestions']:
                        st.info(suggestion)
                        
            else:
                st.error(f"Verification failed: {response.text}")
                
        except Exception as e:
            st.error(f"Error: {str(e)}")

def show_test_scenarios():
    st.header("🧪 Test Scenario Generation & Testing")
    st.markdown("""
    Generate comprehensive test scenarios for your policies and validate them individually or in bulk.
    **Workflow:** First generate scenarios, then test them individually or all at once.
    This creates test cases covering all edge cases including missing mandatory variables,
    valid scenarios, rule violations, and boundary conditions.
    """)
    
    # Policy selection
    st.subheader("Select Policy")
    
    try:
        # Fetch available policies
        response = requests.get(f"{API_BASE_URL}{API_V1_PREFIX}/policies/")
        if response.status_code == 200:
            policies = response.json()
            compiled_policies = [p for p in policies if p.get('status') == 'compiled']
            
            if not compiled_policies:
                st.warning("No compiled policies found. Please compile a policy first.")
                return
                
            policy_options = {f"{p['name']} (v{p['version']})": p['id'] for p in compiled_policies}
            selected_policy_name = st.selectbox("Choose a policy", list(policy_options.keys()))
            
            if selected_policy_name:
                selected_policy_id = policy_options[selected_policy_name]
                selected_policy = next(p for p in compiled_policies if p['id'] == selected_policy_id)
                
                # Show policy details
                with st.expander("Policy Details", expanded=False):
                    st.json(selected_policy)
                
                # Test scenario configuration
                st.subheader("Configuration")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    max_scenarios = st.slider(
                        "Max scenarios per category", 
                        min_value=1, 
                        max_value=5, 
                        value=1,
                        help="Maximum number of scenarios to generate for each category (set to 1 for demo)"
                    )
                
                with col2:
                    categories = st.multiselect(
                        "Categories to include",
                        ["missing_mandatory", "valid_scenarios", "rule_violations", "edge_cases"],
                        default=["missing_mandatory", "valid_scenarios", "rule_violations", "edge_cases"],
                        help="Select which types of test scenarios to generate"
                    )
                
                # Initialize session state for test scenario flow
                if 'generated_scenarios' not in st.session_state:
                    st.session_state.generated_scenarios = None
                    st.session_state.test_results = {}
                    st.session_state.current_policy_id = None
                    st.session_state.testing_in_progress = False
                    st.session_state.test_completed = False
                
                # Clear scenarios if different policy selected
                if st.session_state.current_policy_id != selected_policy_id:
                    st.session_state.generated_scenarios = None
                    st.session_state.test_results = {}
                    st.session_state.current_policy_id = selected_policy_id
                    st.session_state.testing_in_progress = False
                    st.session_state.test_completed = False
                
                # Step-by-step UI flow
                st.markdown("---")
                
                # Step 1: Generate scenarios
                st.markdown("### 📝 Step 1: Generate Test Scenarios")
                generate_scenarios = st.button("🔄 Generate Test Scenarios", use_container_width=True, type="primary")
                
                if not st.session_state.generated_scenarios:
                    st.info("Click above to generate comprehensive test scenarios for your policy")
                else:
                    st.success(f"✅ Generated {len(st.session_state.generated_scenarios['scenarios'])} scenarios")
                
                # Step 2 & 3: Review and Test scenarios (only show if generated)
                if st.session_state.generated_scenarios:
                    st.markdown("### 📋 Step 2: Review Generated Scenarios")
                    scenarios = st.session_state.generated_scenarios["scenarios"]
                    
                    # Show brief summary
                    metadata = st.session_state.generated_scenarios["metadata"]
                    col1, col2, col3, col4 = st.columns(4)
                    for i, (category, count) in enumerate(metadata["categories"].items()):
                        with [col1, col2, col3, col4][i % 4]:
                            st.metric(category.replace("_", " ").title(), count)
                    
                    st.markdown("---")
                    
                    # Step 3: Test scenarios - make it prominent
                    st.markdown("### 🧪 Step 3: Test All Scenarios")
                    
                    # Show test button or results
                    if not st.session_state.test_completed and not st.session_state.testing_in_progress:
                        st.info("✨ Your scenarios are ready! Click below to test them against your policy.")
                        test_scenarios = st.button("🚀 Test All Generated Scenarios", use_container_width=True, type="primary")
                        if test_scenarios:
                            st.session_state.testing_in_progress = True
                            st.rerun()
                    elif st.session_state.testing_in_progress:
                        st.info("🔄 Testing in progress... Please wait.")
                        st.button("⏳ Testing...", disabled=True, use_container_width=True)
                    else:
                        st.success("✅ Testing completed! See detailed results below.")
                        if st.button("🔄 Test Again", type="secondary"):
                            st.session_state.test_completed = False
                            st.session_state.test_results = {}
                            st.session_state.testing_in_progress = False
                            st.rerun()
                else:
                    st.markdown("### 🧪 Step 2: Test Scenarios")
                    st.info("⬆️ Generate test scenarios first to see the test button")
                
                # Generate scenarios
                if generate_scenarios:
                    with st.spinner("Generating test scenarios..."):
                        try:
                            payload = {
                                "max_scenarios_per_category": max_scenarios,
                                "include_categories": categories
                            }
                            
                            response = requests.post(
                                f"{API_BASE_URL}{API_V1_PREFIX}/policies/{selected_policy_id}/generate-test-scenarios",
                                json=payload
                            )
                            
                            if response.status_code == 200:
                                result = response.json()
                                st.session_state.generated_scenarios = result
                                st.session_state.test_results = {}  # Clear previous test results
                                st.session_state.test_completed = False  # Reset test completion
                                st.session_state.testing_in_progress = False  # Reset testing flag
                                
                                # Show metadata
                                metadata = result["metadata"]
                                st.success(f"✅ Generated {metadata['total_scenarios']} test scenarios successfully!")
                                
                                # Show category breakdown
                                col1, col2, col3, col4 = st.columns(4)
                                for i, (category, count) in enumerate(metadata["categories"].items()):
                                    with [col1, col2, col3, col4][i % 4]:
                                        st.metric(category.replace("_", " ").title(), count)
                                        
                                # Automatically rerun to show the test button
                                st.rerun()
                            else:
                                st.error(f"Failed to generate scenarios: {response.text}")
                                
                        except Exception as e:
                            st.error(f"Error generating scenarios: {str(e)}")
                
                # Execute testing if flag is set
                if st.session_state.testing_in_progress and st.session_state.generated_scenarios:
                    scenarios = st.session_state.generated_scenarios["scenarios"]
                    
                    # Show progress container
                    progress_container = st.container()
                    with progress_container:
                        st.info(f"Testing {len(scenarios)} scenarios...")
                        progress_bar = st.progress(0)
                        status_text = st.empty()
                    
                    test_results = []
                    for idx, scenario in enumerate(scenarios):
                        # Update progress
                        progress = (idx + 1) / len(scenarios)
                        progress_bar.progress(progress)
                        status_text.text(f"Testing scenario {idx + 1}/{len(scenarios)}: {scenario['question'][:50]}...")
                        
                        # Test the scenario
                        verify_payload = {
                            "question": scenario["question"],
                            "answer": scenario["answer"]
                        }
                        
                        try:
                            response = requests.post(
                                f"{API_BASE_URL}{API_V1_PREFIX}/policies/{selected_policy_id}/verify",
                                json=verify_payload,
                                timeout=30  # Add timeout for better UX
                            )
                            
                            if response.status_code == 200:
                                result = response.json()
                                actual_result = result.get("result", "error")
                                expected_result = scenario.get("expected_result", "valid")
                                passed = actual_result == expected_result
                                
                                test_result = {
                                    "scenario_id": scenario["id"],
                                    "question": scenario["question"],
                                    "actual_result": actual_result,
                                    "expected_result": expected_result,
                                    "passed": passed,
                                    "explanation": result.get("explanation", "")
                                }
                                test_results.append(test_result)
                                st.session_state.test_results[scenario["id"]] = test_result
                            else:
                                st.error(f"Failed to test scenario {idx+1}: {response.text}")
                        except requests.Timeout:
                            st.error(f"Timeout testing scenario {idx+1}")
                        except Exception as e:
                            st.error(f"Error testing scenario {idx+1}: {str(e)}")
                    
                    # Mark testing as completed
                    st.session_state.testing_in_progress = False
                    st.session_state.test_completed = True
                    
                    # Clear progress indicators and show completion
                    progress_container.empty()
                    st.success(f"✅ Testing completed! {len(test_results)} scenarios tested.")
                    
                    st.rerun()
                
                # Show test results if completed
                if st.session_state.test_completed and st.session_state.test_results:
                    st.markdown("### 📊 Test Results")
                    
                    test_results = list(st.session_state.test_results.values())
                    passed_count = sum(1 for r in test_results if r["passed"])
                    failed_count = len(test_results) - passed_count
                    success_rate = (passed_count / len(test_results) * 100) if test_results else 0
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("✅ Passed", passed_count)
                    with col2:
                        st.metric("❌ Failed", failed_count)
                    with col3:
                        st.metric("Success Rate", f"{success_rate:.1f}%")
                    
                    if success_rate == 100:
                        st.success("🎉 All test scenarios passed!")
                    elif success_rate >= 80:
                        st.warning(f"⚠️ Most scenarios passed ({success_rate:.1f}%)")
                    else:
                        st.error(f"❌ Many scenarios failed ({success_rate:.1f}%)")
                
                # Display detailed results if testing completed
                if st.session_state.test_completed and st.session_state.test_results:
                    st.markdown("### 📝 Detailed Test Results")
                    
                    scenarios = st.session_state.generated_scenarios["scenarios"]
                    
                    for scenario in scenarios:
                        test_result = st.session_state.test_results.get(scenario["id"])
                        
                        if test_result:
                            status_emoji = "✅" if test_result["passed"] else "❌"
                            status_text = "PASSED" if test_result["passed"] else "FAILED"
                            
                            with st.expander(f"{status_emoji} {scenario['name']} - {status_text}", expanded=False):
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    st.markdown("**Question:**")
                                    st.write(scenario["question"])
                                    
                                    st.markdown("**Answer:**")
                                    st.write(scenario["answer"])
                                
                                with col2:
                                    st.markdown("**Expected Result:**")
                                    st.code(scenario["expected_result"])
                                    
                                    st.markdown("**Actual Result:**")
                                    st.code(test_result["actual_result"])
                                    
                                    if not test_result["passed"]:
                                        st.markdown("**Explanation:**")
                                        st.write(test_result["explanation"])
                
                # Display generated scenarios (if not tested yet)
                elif st.session_state.generated_scenarios and not st.session_state.test_completed:
                    st.markdown("### 📋 Generated Scenarios Preview")
                    
                    scenarios = st.session_state.generated_scenarios["scenarios"]
                    
                    for idx, scenario in enumerate(scenarios[:3]):  # Show first 3 as preview
                        with st.expander(f"Preview: {scenario['name']}", expanded=False):
                            st.markdown("**Question:**")
                            st.write(scenario["question"])
                            st.markdown("**Expected Result:**")
                            st.code(scenario["expected_result"])
                    
                    if len(scenarios) > 3:
                        st.info(f"... and {len(scenarios) - 3} more scenarios. Click 'Test All' to see results.")
        
        else:
            st.error(f"Failed to fetch policies: {response.text}")
            
    except Exception as e:
        st.error(f"Error: {str(e)}")

def show_examples():
    st.header("Examples")
    
    st.markdown("""
    Here are some example policies and test scenarios to help you get started.
    """)
    
    # Example policy
    st.subheader("Example: HR Vacation Policy")
    
    example_policy = """
    policy_name: "vacation_request_policy"
    domain: "hr"
    version: "1.0"
    description: "Employee vacation request policy"
    
    variables:
      - name: "advance_notice_days"
        type: "number"
        description: "Days between request submission and vacation start"
      - name: "vacation_duration_days"
        type: "number" 
        description: "Total consecutive days of vacation requested"
      - name: "request_type"
        type: "enum"
        possible_values: ["regular_vacation", "emergency_leave"]
        description: "Type of leave request"
      - name: "has_manager_approval"
        type: "boolean"
        description: "Whether request has manager approval"
    
    rules:
      - id: "advance_notice_rule"
        condition: "request_type == 'regular_vacation' AND advance_notice_days < 14"
        conclusion: "invalid"
        description: "Regular vacation needs 2+ weeks advance notice"
      - id: "manager_approval_rule"  
        condition: "vacation_duration_days > 5 AND NOT has_manager_approval"
        conclusion: "invalid"
        description: "Long vacations need manager approval"
      - id: "emergency_exception_rule"
        condition: "request_type == 'emergency_leave'"
        conclusion: "valid"
        description: "Emergency leave bypasses normal rules"
    
    constraints:
      - "advance_notice_days >= 0"
      - "vacation_duration_days > 0"
    """
    
    st.code(example_policy, language='yaml')
    
    # Example test cases
    st.subheader("Example Test Cases")
    
    test_cases = [
        {
            "name": "Valid regular vacation",
            "question": "Can I take 3 days vacation in 3 weeks?",
            "answer": "Yes, you can take the vacation.",
            "expected": "VALID"
        },
        {
            "name": "Invalid - insufficient notice",
            "question": "Can I take vacation next week?",
            "answer": "Yes, but you only have 5 days notice.",
            "expected": "INVALID"
        },
        {
            "name": "Invalid - long vacation without approval",
            "question": "Can I take 10 days vacation in a month?",
            "answer": "Yes, but you don't have manager approval yet.",
            "expected": "INVALID"
        },
        {
            "name": "Valid emergency leave",
            "question": "I need emergency leave for family situation.",
            "answer": "Emergency leave is approved immediately.",
            "expected": "VALID"
        }
    ]
    
    for case in test_cases:
        with st.expander(f"{case['name']} (Expected: {case['expected']})"):
            st.write(f"**Question:** {case['question']}")
            st.write(f"**Answer:** {case['answer']}")
            st.write(f"**Expected Result:** {case['expected']}")

def delete_policy(policy_id: str):
    """Delete a policy"""
    try:
        response = requests.delete(f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}")
        if response.status_code == 200:
            st.success("Policy deleted successfully!")
            st.rerun()
        else:
            st.error(f"Failed to delete policy: {response.text}")
    except Exception as e:
        st.error(f"Error deleting policy: {str(e)}")

def show_policy_editor():
    """Policy editor interface"""
    st.header("✏️ Policy Editor")
    
    # Check if redirected from policy management
    if st.session_state.get('redirect_to_editor', False):
        policy_id = st.session_state.get('selected_policy_for_editing')
        st.session_state.redirect_to_editor = False
    else:
        policy_id = None
    
    # Policy selection
    col1, col2 = st.columns([2, 1])
    
    with col1:
        policy_id_input = st.text_input(
            "Policy ID to Edit", 
            value=policy_id or "",
            help="Enter the UUID of the policy you want to edit"
        )
    
    with col2:
        if st.button("Create New Policy"):
            st.session_state.creating_new_policy = True
            policy_id_input = ""
    
    # Create new policy form
    if st.session_state.get('creating_new_policy', False):
        show_new_policy_form()
    
    # Edit existing policy
    elif policy_id_input:
        show_edit_policy_form(policy_id_input)

def show_new_policy_form():
    """Form for creating a new policy"""
    st.subheader("Create New Policy")
    
    with st.form("new_policy_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("Policy Name*", placeholder="e.g., Expense Approval Policy")
            domain = st.selectbox("Domain*", ["hr", "legal", "finance", "operations", "compliance", "security", "other"])
            version = st.text_input("Version", value="1.0")
        
        with col2:
            description = st.text_area("Description", placeholder="Brief description of the policy...")
        
        st.subheader("Variables")
        
        # Variables editor (simplified)
        num_vars = st.number_input("Number of Variables", min_value=1, max_value=20, value=3)
        variables = []
        
        for i in range(num_vars):
            st.write(f"**Variable {i+1}:**")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                var_name = st.text_input(f"Name", key=f"var_name_{i}", placeholder="variable_name")
                var_type = st.selectbox(f"Type", ["string", "number", "boolean", "enum", "date"], key=f"var_type_{i}")
            
            with col2:
                var_desc = st.text_input(f"Description", key=f"var_desc_{i}", placeholder="What this variable represents")
                is_mandatory = st.checkbox(f"Mandatory", key=f"var_mandatory_{i}", value=True, 
                                          help="If unchecked, rules using this variable will be skipped when the variable is unknown")
            
            with col3:
                if var_type == "enum":
                    possible_values = st.text_input(f"Possible Values", key=f"var_vals_{i}", 
                                                   placeholder="value1,value2,value3")
                    possible_values = [v.strip() for v in possible_values.split(",") if v.strip()] if possible_values else []
                else:
                    possible_values = []
            
            with col4:
                default_value = st.text_input(f"Default Value", key=f"var_default_{i}", 
                                            placeholder="Leave empty for no default",
                                            help="Used when variable cannot be extracted from text")
            
            if var_name and var_desc:
                var_dict = {
                    "name": var_name,
                    "type": var_type,
                    "description": var_desc,
                    "possible_values": possible_values,
                    "is_mandatory": is_mandatory
                }
                
                if default_value.strip():
                    var_dict["default_value"] = default_value.strip()
                
                variables.append(var_dict)
        
        st.subheader("Rules")
        
        # Rules editor (simplified)
        num_rules = st.number_input("Number of Rules", min_value=1, max_value=20, value=2)
        rules = []
        
        for i in range(num_rules):
            st.write(f"**Rule {i+1}:**")
            col1, col2 = st.columns(2)
            
            with col1:
                rule_id = st.text_input(f"Rule ID", key=f"rule_id_{i}", placeholder="rule_identifier")
                rule_desc = st.text_input(f"Description", key=f"rule_desc_{i}", placeholder="What this rule enforces")
            
            with col2:
                rule_condition = st.text_input(f"Condition", key=f"rule_cond_{i}", 
                                              placeholder="variable1 == 'value' AND variable2 > 10")
                rule_conclusion = st.selectbox(f"Conclusion", ["valid", "invalid"], key=f"rule_conc_{i}")
            
            if rule_id and rule_desc and rule_condition:
                rules.append({
                    "id": rule_id,
                    "description": rule_desc,
                    "condition": rule_condition,
                    "conclusion": rule_conclusion,
                    "priority": i + 1
                })
        
        st.subheader("Constraints")
        constraints_text = st.text_area("Global Constraints (one per line)", 
                                       placeholder="variable1 > 0\nvariable2 <= 100")
        constraints = [c.strip() for c in constraints_text.split("\n") if c.strip()] if constraints_text else []
        
        submitted = st.form_submit_button("Create Policy")
        
        if submitted and name and domain and variables and rules:
            policy_data = {
                "name": name,
                "domain": domain,
                "version": version,
                "description": description,
                "variables": variables,
                "rules": rules,
                "constraints": constraints
            }
            
            try:
                response = requests.post(f"{API_BASE_URL}{API_V1_PREFIX}/policies/", json=policy_data)
                if response.status_code == 200:
                    result = response.json()
                    st.success(f"✅ Policy created successfully! ID: {result['id']}")
                    st.session_state.creating_new_policy = False
                    st.rerun()
                else:
                    st.error(f"Failed to create policy: {response.text}")
            except Exception as e:
                st.error(f"Error creating policy: {str(e)}")

def show_edit_policy_form(policy_id: str):
    """Form for editing an existing policy"""
    try:
        response = requests.get(f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}")
        if response.status_code != 200:
            st.error(f"Policy not found: {response.status_code} - {response.text}")
            return
        
        policy = response.json()
        
        st.subheader(f"Edit Policy: {policy['name']}")
        
        # Show tabs for different editing modes
        tab1, tab2, tab3 = st.tabs(["📋 Structured Edit", "🔧 JSON Edit", "📊 Policy View"])
        
        with tab1:
            # Structured editing form
            with st.form(f"edit_policy_{policy_id}"):
                col1, col2 = st.columns(2)
                
                with col1:
                    name = st.text_input("Policy Name", value=policy['name'])
                    domain = st.selectbox("Domain", 
                                        ["hr", "legal", "finance", "operations", "compliance", "security", "other"],
                                        index=["hr", "legal", "finance", "operations", "compliance", "security", "other"].index(policy['domain']) if policy['domain'] in ["hr", "legal", "finance", "operations", "compliance", "security", "other"] else 0)
                    version = st.text_input("Version", value=policy['version'])
                
                with col2:
                    description = st.text_area("Description", value=policy['description'] or "")
                
                st.subheader("Variables")
                
                # Show existing variables
                variables = policy['variables'] or []
                st.write(f"**Current Variables ({len(variables)}):**")
                
                for i, var in enumerate(variables):
                    mandatory_status = "🔴 MANDATORY" if var.get('is_mandatory', True) else "🟢 OPTIONAL"
                    with st.expander(f"Variable: {var['name']} ({var['type']}) - {mandatory_status}"):
                        st.write(f"**Description:** {var['description']}")
                        st.write(f"**Status:** {mandatory_status}")
                        if var.get('possible_values'):
                            st.write(f"**Possible Values:** {var['possible_values']}")
                        if var.get('default_value'):
                            st.write(f"**Default Value:** {var['default_value']}")
                        elif not var.get('is_mandatory', True):
                            st.warning("⚠️ No default value - rules using this variable will be skipped if unknown")
                
                st.subheader("Rules") 
                
                # Show existing rules
                rules = policy['rules'] or []
                st.write(f"**Current Rules ({len(rules)}):**")
                
                for i, rule in enumerate(rules):
                    with st.expander(f"Rule: {rule['id']} - {rule['conclusion']}"):
                        st.write(f"**Description:** {rule['description']}")
                        st.code(f"Condition: {rule['condition']}")
                        st.write(f"**Conclusion:** {rule['conclusion']}")
                        st.write(f"**Priority:** {rule['priority']}")
                
                st.subheader("Constraints")
                constraints_text = st.text_area("Global Constraints (one per line)", 
                                               value='\n'.join(policy['constraints'] or []))
                
                submitted = st.form_submit_button("Update Policy (Basic)")
                
                if submitted:
                    updated_policy = {
                        "name": name,
                        "domain": domain,
                        "version": version,
                        "description": description,
                        "variables": variables,  # Keep existing variables
                        "rules": rules,          # Keep existing rules
                        "constraints": [c.strip() for c in constraints_text.split('\n') if c.strip()]
                    }
                    
                    try:
                        response = requests.put(
                            f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}",
                            json=updated_policy
                        )
                        
                        if response.status_code == 200:
                            st.success("✅ Policy updated successfully!")
                            st.rerun()
                        else:
                            st.error(f"Failed to update policy: {response.text}")
                    except Exception as e:
                        st.error(f"Error updating policy: {str(e)}")
        
        with tab2:
            # JSON editing (advanced)
            st.warning("⚠️ Advanced feature: Edit the policy JSON directly. Make sure to maintain proper structure.")
            
            policy_json = st.text_area(
                "Policy JSON", 
                value=json.dumps(policy, indent=2),
                height=500,
                help="Edit the policy structure. Be careful with the JSON format!"
            )
            
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("Update Policy (JSON)", key="json_update"):
                    try:
                        updated_policy = json.loads(policy_json)
                        # Remove read-only fields
                        for field in ['id', 'document_id', 'created_at', 'updated_at', 'status']:
                            updated_policy.pop(field, None)
                        
                        response = requests.put(
                            f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}",
                            json=updated_policy
                        )
                        
                        if response.status_code == 200:
                            st.success("✅ Policy updated successfully!")
                            st.rerun()
                        else:
                            st.error(f"Failed to update policy: {response.text}")
                            
                    except json.JSONDecodeError as e:
                        st.error(f"Invalid JSON format: {str(e)}")
                    except Exception as e:
                        st.error(f"Error updating policy: {str(e)}")
            
            with col2:
                if st.button("Validate JSON", key="validate_json"):
                    try:
                        json.loads(policy_json)
                        st.success("✅ JSON is valid")
                    except json.JSONDecodeError as e:
                        st.error(f"❌ JSON error: {str(e)}")
        
        with tab3:
            # Policy viewing (detailed)
            show_detailed_policy_view(policy)
            
    except Exception as e:
        st.error(f"Error loading policy: {str(e)}")

def show_detailed_policy_view(policy: dict):
    """Show detailed policy information in a structured way"""
    st.subheader("📊 Policy Details")
    
    # Basic info
    col1, col2 = st.columns(2)
    
    with col1:
        st.metric("Domain", policy['domain'].title())
        st.metric("Version", policy['version'])
        st.metric("Status", policy['status'].title())
    
    with col2:
        st.metric("Variables", len(policy.get('variables', [])))
        st.metric("Rules", len(policy.get('rules', []))) 
        st.metric("Constraints", len(policy.get('constraints', [])))
    
    # Description
    if policy.get('description'):
        st.write("**Description:**")
        st.info(policy['description'])
    
    # Variables section
    if policy.get('variables'):
        st.subheader("🔢 Variables")
        
        # Add new variable section
        st.subheader("➕ Add New Variable")
        with st.expander("Add Variable"):
            with st.form("add_variable_form"):
                col1, col2 = st.columns(2)
                with col1:
                    new_var_name = st.text_input("Variable Name", placeholder="employee_id")
                    new_var_type = st.selectbox("Type", ["string", "number", "boolean", "enum", "date"])
                    new_var_description = st.text_input("Description", placeholder="Description for variable extraction")
                    
                with col2:
                    new_var_mandatory = st.checkbox("Is Mandatory", value=True)
                    new_var_default = st.text_input("Default Value (optional)", placeholder="Leave empty for no default")
                    if new_var_type == "enum":
                        new_var_values = st.text_input("Possible Values", placeholder="value1,value2,value3")
                    else:
                        new_var_values = ""
                
                if st.form_submit_button("Add Variable"):
                    if add_variable(policy.get('id'), new_var_name, new_var_type, new_var_description, 
                                   new_var_mandatory, new_var_default, new_var_values):
                        st.success(f"Variable '{new_var_name}' added!")
                        st.rerun()

        # Existing variables with enhanced editing
        for i, var in enumerate(policy['variables']):
            with st.container():
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                
                with col1:
                    # Variable info with edit mode
                    if f"edit_var_{var['name']}" not in st.session_state:
                        st.session_state[f"edit_var_{var['name']}"] = False
                    
                    if not st.session_state[f"edit_var_{var['name']}"]:
                        # Display mode
                        mandatory_indicator = "🔴 MANDATORY" if var.get('is_mandatory', True) else "🟢 OPTIONAL"
                        st.write(f"**{var['name']}** (`{var['type']}`) - {mandatory_indicator}")
                        st.write(f"📝 {var['description']}")
                        
                        if var.get('possible_values'):
                            st.write(f"✅ Possible values: `{', '.join(map(str, var['possible_values']))}`")
                        
                        if var.get('default_value'):
                            st.write(f"🎯 Default value: `{var['default_value']}`")
                        elif not var.get('is_mandatory', True):
                            st.write(f"⚠️ No default - rules using this variable will be skipped if unknown")
                    else:
                        # Edit mode
                        new_description = st.text_input("Description", value=var['description'], 
                                                       key=f"edit_desc_{var['name']}_{i}")
                        if var['type'] == 'enum' and var.get('possible_values'):
                            new_values = st.text_input("Possible Values", 
                                                     value=','.join(var['possible_values']),
                                                     key=f"edit_values_{var['name']}_{i}")
                        
                with col2:
                    # Mandatory toggle
                    current_mandatory = var.get('is_mandatory', True)
                    new_mandatory = st.toggle(
                        "Mandatory", 
                        value=current_mandatory,
                        key=f"mandatory_{var['name']}_{i}"
                    )
                    
                    if new_mandatory != current_mandatory:
                        if update_variable_property(policy.get('id'), var['name'], 'is_mandatory', new_mandatory):
                            st.success(f"Updated {var['name']} mandatory status!")
                            st.rerun()
                
                with col3:
                    # Default value editor
                    if not var.get('is_mandatory', True):
                        current_default = var.get('default_value', '')
                        new_default = st.text_input(
                            "Default", 
                            value=current_default,
                            key=f"default_{var['name']}_{i}",
                            placeholder="No default"
                        )
                        
                        if st.button("💾", key=f"update_default_{var['name']}_{i}", help="Update default"):
                            if update_variable_property(policy.get('id'), var['name'], 'default_value', new_default):
                                st.success(f"Updated {var['name']} default!")
                                st.rerun()
                
                with col4:
                    # Action buttons
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("✏️", key=f"edit_btn_{var['name']}_{i}", help="Edit variable"):
                            st.session_state[f"edit_var_{var['name']}"] = not st.session_state[f"edit_var_{var['name']}"]
                            st.rerun()
                    
                    with btn_col2:
                        if st.button("🗑️", key=f"delete_btn_{var['name']}_{i}", help="Delete variable"):
                            if st.session_state.get(f"confirm_delete_{var['name']}", False):
                                if delete_variable(policy.get('id'), var['name']):
                                    st.success(f"Deleted {var['name']}!")
                                    st.rerun()
                            else:
                                st.session_state[f"confirm_delete_{var['name']}"] = True
                                st.warning(f"Click again to confirm deletion of {var['name']}")
                
                st.divider()
    
    # Rules section with full CRUD
    st.subheader("⚖️ Rules")
    
    # Add new rule section
    st.subheader("➕ Add New Rule")
    with st.expander("Add Rule"):
        with st.form("add_rule_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_rule_id = st.text_input("Rule ID", placeholder="rule_001")
                new_rule_description = st.text_input("Description", placeholder="Human-readable description")
                new_rule_condition = st.text_area("Condition", placeholder="employee_type == 'full_time' AND tenure_years >= 2")
            
            with col2:
                new_rule_conclusion = st.selectbox("Conclusion", ["valid", "invalid"])
                new_rule_priority = st.number_input("Priority", min_value=1, max_value=100, value=1)
            
            if st.form_submit_button("Add Rule"):
                if add_rule(policy.get('id'), new_rule_id, new_rule_description, 
                           new_rule_condition, new_rule_conclusion, new_rule_priority):
                    st.success(f"Rule '{new_rule_id}' added!")
                    st.rerun()

    # Existing rules with enhanced editing
    if policy.get('rules'):
        for i, rule in enumerate(policy['rules']):
            conclusion_emoji = "✅" if rule.get('conclusion') == 'valid' else "❌"
            
            with st.container():
                col1, col2 = st.columns([4, 1])
                
                with col1:
                    # Rule info with edit mode
                    if f"edit_rule_{rule['id']}" not in st.session_state:
                        st.session_state[f"edit_rule_{rule['id']}"] = False
                    
                    if not st.session_state[f"edit_rule_{rule['id']}"]:
                        # Display mode
                        st.write(f"{conclusion_emoji} **{rule['id']}**: {rule['description']} (Priority: {rule.get('priority', 'N/A')})")
                        st.code(f"IF {rule['condition']} THEN {rule['conclusion']}")
                    else:
                        # Edit mode
                        with st.form(f"edit_rule_form_{i}"):
                            edit_col1, edit_col2 = st.columns(2)
                            with edit_col1:
                                new_description = st.text_input("Description", value=rule['description'])
                                new_condition = st.text_area("Condition", value=rule['condition'])
                            
                            with edit_col2:
                                new_conclusion = st.selectbox("Conclusion", ["valid", "invalid"], 
                                                            index=0 if rule['conclusion'] == 'valid' else 1)
                                new_priority = st.number_input("Priority", min_value=1, max_value=100, 
                                                             value=rule.get('priority', 1))
                            
                            if st.form_submit_button("Save Changes"):
                                if update_rule(policy.get('id'), rule['id'], new_description, 
                                              new_condition, new_conclusion, new_priority):
                                    st.success(f"Rule '{rule['id']}' updated!")
                                    st.session_state[f"edit_rule_{rule['id']}"] = False
                                    st.rerun()
                
                with col2:
                    # Action buttons
                    btn_col1, btn_col2 = st.columns(2)
                    with btn_col1:
                        if st.button("✏️", key=f"edit_rule_btn_{rule['id']}_{i}", help="Edit rule"):
                            st.session_state[f"edit_rule_{rule['id']}"] = not st.session_state[f"edit_rule_{rule['id']}"]
                            st.rerun()
                    
                    with btn_col2:
                        if st.button("🗑️", key=f"delete_rule_btn_{rule['id']}_{i}", help="Delete rule"):
                            if st.session_state.get(f"confirm_delete_rule_{rule['id']}", False):
                                if delete_rule(policy.get('id'), rule['id']):
                                    st.success(f"Deleted rule '{rule['id']}'!")
                                    st.rerun()
                            else:
                                st.session_state[f"confirm_delete_rule_{rule['id']}"] = True
                                st.warning(f"Click again to confirm deletion of rule '{rule['id']}'")
                
                st.divider()
    
    # Constraints section with CRUD
    st.subheader("🔒 Global Constraints")
    
    # Add new constraint section
    st.subheader("➕ Add New Constraint")
    with st.expander("Add Constraint"):
        with st.form("add_constraint_form"):
            new_constraint = st.text_input("Constraint", placeholder="variable_name > 0")
            st.help("Examples: employee_age >= 18, salary > 0, tenure_months >= 1")
            
            if st.form_submit_button("Add Constraint"):
                if add_constraint(policy.get('id'), new_constraint):
                    st.success(f"Constraint added!")
                    st.rerun()

    # Existing constraints
    if policy.get('constraints'):
        for i, constraint in enumerate(policy['constraints']):
            col1, col2 = st.columns([4, 1])
            
            with col1:
                st.code(constraint)
            
            with col2:
                if st.button("🗑️", key=f"delete_constraint_{i}", help="Delete constraint"):
                    if st.session_state.get(f"confirm_delete_constraint_{i}", False):
                        if delete_constraint(policy.get('id'), constraint):
                            st.success("Constraint deleted!")
                            st.rerun()
                    else:
                        st.session_state[f"confirm_delete_constraint_{i}"] = True
                        st.warning("Click again to confirm deletion")
    else:
        st.info("No constraints defined. Constraints help validate variable values.")
    
    # Examples section
    if policy.get('examples'):
        st.subheader("💡 Examples")
        for example in policy['examples']:
            with st.expander(f"Example: {example.get('expected_result', 'Unknown').title()}"):
                st.write(f"**Question:** {example.get('question', 'N/A')}")
                if example.get('variables'):
                    st.write("**Variables:**")
                    for var_name, var_value in example['variables'].items():
                        st.write(f"- {var_name}: `{var_value}`")
                st.write(f"**Expected Result:** {example.get('expected_result', 'N/A')}")
                if example.get('explanation'):
                    st.write(f"**Explanation:** {example['explanation']}")
    
    # Policy health check
    st.subheader("🏥 Policy Health Check")
    
    if st.button("Analyze Policy", key=f"analyze_{policy.get('id', 'unknown')}"):
        try:
            response = requests.get(f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy['id']}/variable-analysis")
            if response.status_code == 200:
                analysis = response.json()
                
                st.write("**Variable Analysis:**")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Defined Variables", analysis['total_defined_variables'])
                with col2:
                    st.metric("Referenced Variables", analysis['total_referenced_variables']) 
                with col3:
                    missing_count = len(analysis['missing_variables'])
                    st.metric("Missing Variables", missing_count, delta=-missing_count if missing_count > 0 else None)
                
                if analysis['missing_variables']:
                    st.warning(f"⚠️ Missing variables: {', '.join(analysis['missing_variables'])}")
                    if st.button("Auto-Fix Missing Variables", key=f"autofix_{policy.get('id', 'unknown')}"):
                        fix_response = requests.post(f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy['id']}/fix-missing-variables?auto_add=true")
                        if fix_response.status_code == 200:
                            fix_result = fix_response.json()
                            st.success(f"✅ {fix_result['message']}")
                            st.rerun()
                        else:
                            st.error(f"Failed to fix variables: {fix_response.text}")
                
                if analysis['unused_variables']:
                    st.info(f"ℹ️ Unused variables: {', '.join(analysis['unused_variables'])}")
                    
                if not analysis['missing_variables'] and not analysis['unused_variables']:
                    st.success("✅ All variables are properly defined and used!")
                    
        except Exception as e:
            st.error(f"Error analyzing policy: {str(e)}")

def show_database_inspector():
    """Database inspection interface"""
    st.header("🗄️ Database Inspector")
    
    st.markdown("""
    Explore the contents of the database to understand what data is being stored
    and how the system is working internally.
    """)
    
    # Tabs for different data types
    tab1, tab2, tab3, tab4 = st.tabs(["📄 Documents", "📋 Policies", "🔧 Compilations", "✅ Verifications"])
    
    with tab1:
        show_documents_table()
    
    with tab2:
        show_policies_table()
    
    with tab3:
        show_compilations_table()
    
    with tab4:
        show_verifications_table()

def show_documents_table():
    """Show documents in database"""
    st.subheader("Policy Documents")
    
    if st.button("Load Documents", key="load_docs"):
        try:
            response = requests.get(f"{API_BASE_URL}{API_V1_PREFIX}/documents/")
            if response.status_code == 200:
                documents = response.json()
                
                if documents:
                    import pandas as pd
                    df = pd.DataFrame(documents)
                    
                    # Select relevant columns
                    display_columns = ['id', 'filename', 'domain', 'uploaded_at']
                    if all(col in df.columns for col in display_columns):
                        df_display = df[display_columns]
                        st.dataframe(df_display, use_container_width=True)
                    else:
                        st.dataframe(df, use_container_width=True)
                    
                    st.info(f"Total documents: {len(documents)}")
                else:
                    st.info("No documents found")
            else:
                st.error("Failed to fetch documents")
        except Exception as e:
            st.error(f"Error: {str(e)}")

def show_policies_table():
    """Show policies in database"""
    st.subheader("Policies")
    
    if st.button("Load Policies", key="load_policies"):
        try:
            response = requests.get(f"{API_BASE_URL}{API_V1_PREFIX}/policies/")
            if response.status_code == 200:
                policies = response.json()
                
                if policies:
                    import pandas as pd
                    
                    # Flatten the data for table display
                    policy_data = []
                    for policy in policies:
                        policy_data.append({
                            'ID': policy['id'],
                            'Name': policy['name'],
                            'Domain': policy['domain'],
                            'Status': policy['status'],
                            'Version': policy['version'],
                            'Variables': len(policy.get('variables', [])),
                            'Rules': len(policy.get('rules', [])),
                            'Created': policy['created_at']
                        })
                    
                    df = pd.DataFrame(policy_data)
                    st.dataframe(df, use_container_width=True)
                    
                    st.info(f"Total policies: {len(policies)}")
                else:
                    st.info("No policies found")
            else:
                st.error("Failed to fetch policies")
        except Exception as e:
            st.error(f"Error: {str(e)}")

def show_compilations_table():
    """Show compilations in database"""
    st.subheader("Policy Compilations")
    
    policy_id = st.text_input("Policy ID (optional)", help="Leave empty to see all compilations")
    
    if st.button("Load Compilations", key="load_compilations"):
        try:
            if policy_id:
                response = requests.get(f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/compilations")
            else:
                # We'll need to implement an endpoint to get all compilations
                st.warning("Endpoint to get all compilations not implemented yet. Please provide a policy ID.")
                return
            
            if response.status_code == 200:
                compilations = response.json()
                
                if compilations:
                    import pandas as pd
                    
                    compilation_data = []
                    for comp in compilations:
                        compilation_data.append({
                            'ID': comp['id'],
                            'Policy ID': comp['policy_id'],
                            'Status': comp['compilation_status'],
                            'Has Constraints': 'Yes' if comp.get('z3_constraints') else 'No',
                            'Errors': len(comp.get('compilation_errors', []) or []),
                            'Compiled At': comp['compiled_at']
                        })
                    
                    df = pd.DataFrame(compilation_data)
                    st.dataframe(df, use_container_width=True)
                    
                    st.info(f"Total compilations: {len(compilations)}")
                else:
                    st.info("No compilations found")
            else:
                st.error("Failed to fetch compilations")
        except Exception as e:
            st.error(f"Error: {str(e)}")

def show_verifications_table():
    """Show verifications in database"""
    st.subheader("Policy Verifications")
    
    policy_id = st.text_input("Policy ID (optional)", help="Leave empty to see recent verifications", key="verif_policy_id")
    
    col1, col2 = st.columns(2)
    with col1:
        limit = st.number_input("Limit", min_value=10, max_value=1000, value=50)
    with col2:
        result_filter = st.selectbox("Result Filter", ["all", "valid", "invalid", "error", "needs_clarification"])
    
    if st.button("Load Verifications", key="load_verifications"):
        try:
            if policy_id:
                params = {"limit": limit}
                if result_filter != "all":
                    params["result_filter"] = result_filter
                
                response = requests.get(
                    f"{API_BASE_URL}{API_V1_PREFIX}/policies/{policy_id}/verifications",
                    params=params
                )
            else:
                st.warning("Please provide a policy ID to view verifications")
                return
            
            if response.status_code == 200:
                verifications = response.json()
                
                if verifications:
                    import pandas as pd
                    
                    verif_data = []
                    for verif in verifications:
                        verif_data.append({
                            'ID': verif['id'],
                            'Result': verif['verification_result'],
                            'Question': verif['question'][:100] + '...' if len(verif['question']) > 100 else verif['question'],
                            'Answer': verif['answer'][:50] + '...' if len(verif['answer']) > 50 else verif['answer'],
                            'Variables': len(verif.get('extracted_variables', {}) or {}),
                            'Verified At': verif['verified_at']
                        })
                    
                    df = pd.DataFrame(verif_data)
                    st.dataframe(df, use_container_width=True)
                    
                    # Show detailed view for selected verification
                    selected_indices = st.multiselect(
                        "Select verification IDs to view details:",
                        options=range(len(verifications)),
                        format_func=lambda x: f"{verifications[x]['id'][:8]}... - {verifications[x]['verification_result']}"
                    )
                    
                    for idx in selected_indices:
                        verif = verifications[idx]
                        with st.expander(f"Details: {verif['id']}"):
                            st.write(f"**Question:** {verif['question']}")
                            st.write(f"**Answer:** {verif['answer']}")
                            st.write(f"**Result:** {verif['verification_result']}")
                            
                            if verif.get('extracted_variables'):
                                st.write("**Extracted Variables:**")
                                for var, val in verif['extracted_variables'].items():
                                    st.write(f"- {var}: {val}")
                            
                            if verif.get('explanation'):
                                st.write(f"**Explanation:** {verif['explanation']}")
                    
                    st.info(f"Total verifications: {len(verifications)}")
                else:
                    st.info("No verifications found")
            else:
                st.error("Failed to fetch verifications")
        except Exception as e:
            st.error(f"Error: {str(e)}")

if __name__ == "__main__":
    # Check for missing dependencies
    try:
        import pandas as pd
    except ImportError:
        st.error("Please install pandas: pip install pandas")
        st.stop()
    
    main() 