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
        ["🏠 Dashboard", "📄 Document Upload", "📋 Policy Management", "🔧 Compilation", "✅ Verification", "💡 Examples"]
    )
    
    if page == "🏠 Dashboard":
        show_dashboard()
    elif page == "📄 Document Upload":
        show_document_upload()
    elif page == "📋 Policy Management":
        show_policy_management()
    elif page == "🔧 Compilation":
        show_compilation()
    elif page == "✅ Verification":
        show_verification()
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
                                    show_policy_details(policy['id'])
                            
                            with col4:
                                if policy['status'] == 'draft' and st.button(f"Compile", key=f"compile_{policy['id']}"):
                                    compile_policy(policy['id'])
                            
                            with col5:
                                if policy['status'] == 'compiled' and st.button(f"Test Verify", key=f"verify_{policy['id']}"):
                                    st.session_state.selected_policy_for_verification = policy['id']
                else:
                    st.info("No policies found. Upload a document to generate policies.")
            else:
                st.error("Failed to fetch policies")
                
        except Exception as e:
            st.error(f"Error: {str(e)}")

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
    
    # Q&A input
    col1, col2 = st.columns(2)
    
    with col1:
        question = st.text_area("Question", 
                               placeholder="e.g., Can I take 5 days vacation next week?",
                               help="Enter a natural language question about the policy")
    
    with col2:
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
                
                # Show extracted variables
                st.subheader("Extracted Variables")
                if result['extracted_variables']:
                    for var, value in result['extracted_variables'].items():
                        st.write(f"- **{var}**: {value}")
                
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

if __name__ == "__main__":
    main() 