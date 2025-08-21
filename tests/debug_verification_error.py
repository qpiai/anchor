#!/usr/bin/env python3
"""
Debug the verification error step by step
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.variable_extractor import VariableExtractorService
from app.services.verification import VerificationService
from app.services.rule_compiler import RuleCompiler
import asyncio
import requests

# Configuration
API_BASE_URL = "http://localhost:9066"
API_V1_PREFIX = "/api/v1"
POLICY_ID = "adf95535-0103-485f-a202-87cdac80e78e"

async def debug_verification_step_by_step():
    """Debug each step of the verification process"""
    
    print("🔍 Debugging Verification Error Step by Step")
    print("=" * 60)
    
    question = "Can a full-time employee claim $45 for meals with receipts submitted via the Finance Portal within 20 days?"
    answer = "Yes"
    
    # Step 1: Get policy
    print("\n📋 Step 1: Get Policy")
    response = requests.get(f"{API_BASE_URL}{API_V1_PREFIX}/policies/{POLICY_ID}")
    if response.status_code != 200:
        print(f"❌ Failed to get policy: {response.status_code}")
        return
    
    policy = response.json()
    print(f"✅ Policy retrieved: {policy['name']}")
    print(f"   Variables: {len(policy.get('variables', []))}")
    print(f"   Rules: {len(policy.get('rules', []))}")
    
    # Step 2: Test Variable Extraction
    print("\n🔤 Step 2: Test Variable Extraction")
    try:
        extractor = VariableExtractorService()
        extracted = await extractor.extract_variables(question, answer, policy['variables'])
        
        print("✅ Variable extraction successful:")
        for var_name, var_value in extracted.items():
            status = ""
            if var_value == "MISSING_MANDATORY":
                status = " (❌ MISSING MANDATORY)"
            elif var_value == "SKIP_RULE":
                status = " (⏭️ SKIP RULE)"
            elif var_value is None:
                status = " (🟢 NULL)"
            print(f"   - {var_name}: {var_value}{status}")
        
    except Exception as e:
        print(f"❌ Variable extraction failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 3: Test Rule Compilation
    print("\n⚖️ Step 3: Test Rule Compilation")
    try:
        compiler = RuleCompiler()
        compiled = compiler.compile_policy(policy)
        print(f"✅ Rule compilation successful")
        print(f"   Z3 Variables: {len(compiled['variables'])}")
        print(f"   Z3 Rules: {len(compiled['rules'])}")
        print(f"   Z3 Constraints: {len(compiled['constraints'])}")
        
    except Exception as e:
        print(f"❌ Rule compilation failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 4: Test Verification Service
    print("\n🔍 Step 4: Test Verification Service")
    try:
        verifier = VerificationService()
        
        # First try to get the compiled policy from the database
        print("   Getting compiled policy from database...")
        compilations_response = requests.get(f"{API_BASE_URL}{API_V1_PREFIX}/policies/{POLICY_ID}/compilations")
        
        if compilations_response.status_code == 200:
            compilations = compilations_response.json()
            if compilations:
                latest_compilation = max(compilations, key=lambda c: c['compiled_at'])
                if latest_compilation['compilation_status'] == 'success':
                    print(f"   ✅ Found successful compilation: {latest_compilation['id']}")
                    
                    # Try the verification
                    result = verifier.verify_scenario(extracted, latest_compilation['z3_constraints'], policy['rules'])
                    
                    print("✅ Verification successful:")
                    print(f"   Result: {result['result']}")
                    print(f"   Explanation: {result['explanation']}")
                    
                    if 'rule_results' in result:
                        print(f"   Rule Results: {len(result['rule_results'])} rules evaluated")
                        for rule_result in result['rule_results'][:3]:  # Show first 3
                            print(f"     - {rule_result['rule_id']}: {rule_result['result']}")
                    
                else:
                    print(f"   ❌ Latest compilation failed: {latest_compilation['compilation_status']}")
            else:
                print("   ❌ No compilations found")
        else:
            print(f"   ❌ Failed to get compilations: {compilations_response.status_code}")
            
    except Exception as e:
        print(f"❌ Verification failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return
    
    # Step 5: Test Full Integration
    print("\n🔗 Step 5: Test Full Integration via API")
    try:
        verification_data = {
            "question": question,
            "answer": answer
        }
        
        verify_response = requests.post(
            f"{API_BASE_URL}{API_V1_PREFIX}/policies/{POLICY_ID}/verify",
            json=verification_data
        )
        
        if verify_response.status_code == 200:
            result = verify_response.json()
            print("✅ Full API verification successful:")
            print(f"   Result: {result['result']}")
            print(f"   Explanation: {result['explanation']}")
        else:
            print(f"❌ API verification failed: {verify_response.status_code}")
            print(f"   Response: {verify_response.text}")
            
    except Exception as e:
        print(f"❌ API verification error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug_verification_step_by_step())