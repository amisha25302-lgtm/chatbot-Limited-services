import sys
import os
import json
from dotenv import load_dotenv

# Append parent directory to system path to import backend modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import (
    register_user, login_user, UserRegister, UserLogin,
    get_my_applications, get_application_status, get_missing_documents,
    get_pending_applications, get_application_detail_officer, get_sla_status,
    execute_tool, CLAUDE_TOOLS, decode_jwt_token
)

def run_tests():
    print("=== STARTING ROLE-BASED DATA LAYER TESTS ===")
    
    # 1. Test Citizen Authentication
    print("\n[Test 1] Citizen Authentication...")
    login_req = UserLogin(email="ratan1@yahoo.com", password="Citizen1@cg")
    citizen_login = login_user(login_req)
    assert "token" in citizen_login, "Citizen login failed to return token"
    citizen_token = citizen_login["token"]
    citizen_user = citizen_login["user"]
    print("  Citizen Token generated successfully.")
    print("  Citizen Name:", citizen_user["name"])
    assert citizen_user["role"] == "citizen", "Citizen role mismatch"
    
    # Decode JWT to check contents
    decoded_citizen = decode_jwt_token(citizen_token)
    assert decoded_citizen["role"] == "citizen", "Token role must be citizen"
    assert decoded_citizen["user_id"] == citizen_user["user_id"], "Token user_id mismatch"
    
    # 2. Test Officer Authentication
    print("\n[Test 2] Officer Authentication...")
    officer_login = login_user(UserLogin(email="officer5@revenue.cg.gov.in", password="Officer5@cg"))
    assert "token" in officer_login, "Officer login failed to return token"
    officer_token = officer_login["token"]
    officer_user = officer_login["user"]
    print("  Officer Token generated successfully.")
    print("  Officer Name:", officer_user["name"])
    assert officer_user["role"] == "officer", "Officer role mismatch"
    
    decoded_officer = decode_jwt_token(officer_token)
    assert decoded_officer["role"] == "officer", "Token role must be officer"
    assert decoded_officer["officer_id"] == officer_user["officer_id"], "Token officer_id mismatch"
    
    # 3. Test Citizen Data Scoping (get_my_applications)
    print("\n[Test 3] Citizen Data Scoping...")
    ratan_id = citizen_user["user_id"]
    ratan_apps = get_my_applications(ratan_id)
    print(f"  Ratan's Applications: {len(ratan_apps)} found.")
    for app in ratan_apps[:5]: # Show first 5
        print(f"    - App ID: {app['application_id']}, Service: {app['service_name']}, Status: {app['status']}")
        
    citizen_context = {"role": "citizen", "user_id": ratan_id, "officer_id": None}
    res_apps = execute_tool("get_my_applications", {}, citizen_context, "en")
    assert len(res_apps) == len(ratan_apps), "Tool execution output mismatch"
    
    # 4. Test Citizen Application Detail, Status (Expose Reviewing Officer & Document Requests)
    print("\n[Test 4] Citizen Status, Reviewer Officer Field & Document Requests...")
    
    # Target 1: Verify Reviewer Officer details are populated
    target_app_1 = "APP-2026-00123"
    status_res = execute_tool("get_application_status", {"application_id": target_app_1}, citizen_context, "en")
    print(f"  App ID {target_app_1} reviewer name: {status_res.get('reviewer_name')}")
    print(f"  App ID {target_app_1} reviewer designation: {status_res.get('reviewer_designation')}")
    assert status_res.get("reviewer_name") == "Geeta Yadav", "Reviewer name mismatch: expected Geeta Yadav"
    assert status_res.get("reviewer_designation") == "Clerk", "Reviewer designation mismatch: expected Clerk"
    print("    Officer reviewer field verified successfully!")
    
    # Target 2: Verify active document request (status: pending_docs)
    print("  Logging in as Ratan Munda to verify active document request...")
    munda_login = login_user(UserLogin(email="ratan_munda_106", password="Citizen106@cg"))
    munda_context = {"role": "citizen", "user_id": munda_login["user"]["user_id"], "officer_id": None}
    target_app_2 = "APP-2024-01331"
    missing_res = execute_tool("get_missing_documents", {"application_id": target_app_2}, munda_context, "en")
    print(f"  App ID {target_app_2} missing documents list:")
    for doc in missing_res['missing_documents']:
        print(f"    - Document: {doc['document_type']} | Reason: {doc['reason']}")
        if doc['reason'] == "Requested by Officer":
            print("      Verification check passed: active document request detected.")
    
    # 5. Test Officer Queue and Assigned Service Boundary
    print("\n[Test 5] Officer Queue & Service Line Scoping...")
    officer_context = {"role": "officer", "user_id": officer_user["user_id"], "officer_id": officer_user["officer_id"]}
    pending_queue = execute_tool("get_pending_applications", {}, officer_context, "en")
    print(f"  Officer Naresh's Pending Applications Queue: {len(pending_queue)} found.")
    for app in pending_queue:
        print(f"    - App ID: {app['application_id']}, Service: {app['service_name']}, Applicant: {app['applicant_name']}")
        
    # Officer Naresh (dept_id 5) should NOT be allowed to fetch pending queue for Caste Certificate (OBC) (service_id 2, dept_id 1)
    print("  Testing Departmental Boundary (verifying officer cannot fetch other department services)...")
    denied_res = execute_tool("get_pending_applications", {"service_id": 2}, officer_context, "en")
    assert "error" in denied_res, "Officer Naresh should be blocked from querying Caste Certificate (OBC) applications"
    print("    Access successfully denied for unauthorized department service.")
    
    # 6. Test Officer Detail access - Exclude file_path/content (No download links)
    print("\n[Test 6] Officer Detail Access (No file download links/path exposure)...")
    if pending_queue:
        target_app = pending_queue[0]["application_id"]
        detail_res = execute_tool("get_application_detail_officer", {"application_id": target_app}, officer_context, "en")
        print(f"  App ID {target_app} details retrieved for officer successfully.")
        print(f"    Applicant Name: {detail_res['applicant_name']}")
        print(f"    Documents count: {len(detail_res['documents'])}")
        
        # Verify document url/path is excluded
        for doc in detail_res["documents"]:
            assert "file_path" not in doc, "Security Violation: Document file_path was exposed to the officer!"
            assert "url" not in doc, "Security Violation: Document url was exposed to the officer!"
        print("    Security constraint passed: Document URLs are excluded at database query/serialization level.")
        
    # 7. Test SLA Status calculation
    print("\n[Test 7] SLA Status & Breaches...")
    sla_queue = execute_tool("get_sla_status", {}, officer_context, "en")
    found_breach = False
    for app in sla_queue:
        if app["is_breached"]:
            found_breach = True
            print(f"    [BREACHED] App ID: {app['application_id']} (Service: {app['service_name']}) is past deadline {app['sla_deadline']}")
        else:
            print(f"    [Within SLA] App ID: {app['application_id']} (Service: {app['service_name']})")
    assert found_breach, "Expected to find at least one breached application in department 5"
            
    # 8. Test Role-Based Code Level Block
    print("\n[Test 8] Citizen calling Officer Tool is Blocked...")
    blocked_res = execute_tool("get_pending_applications", {}, citizen_context, "en")
    assert blocked_res.get("error") == "Unauthorized.", "Citizen must be blocked from executing officer tools"
    print("    Security constraint passed: Citizen tool-use blocked at code level.")
    
    # 9. Test RAG FAQ Search Tool
    print("\n[Test 9] FAQ RAG Search tool works for everyone...")
    faq_res = execute_tool("faq_search", {"query": "fees for marriage registration"}, citizen_context, "en")
    assert len(faq_res) > 0, "FAQ Search must return RAG context"
    print("    RAG Search succeeded. Retrieved length:", len(faq_res))
    
    print("\n=== ALL TESTS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_tests()
