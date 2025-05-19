import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, auth
import os
import sys
import json
from datetime import datetime, timedelta
import pytz
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Add the timebot library path to Python's path
sys.path.append("/usr/local/lib/timebot/lib")
# Import the config module
from shared.config import config

# Page config
st.set_page_config(
    page_title="User Approval Dashboard",
    page_icon="🔐",
    layout="wide"
)

# Initialize Firebase if not already initialized
if not firebase_admin._apps:
    # Get service account key from config
    service_account_path = config["FIREBASE_SERVICE_ACCOUNT_KEY"]
    
    # Initialize Firebase Admin SDK
    cred = credentials.Certificate(service_account_path)
    firebase_admin.initialize_app(cred, {
        'projectId': config["FIREBASE_PROJECT_ID"],
    })

# Get Firestore client
db = firestore.client()

# Email configuration
FIREBASE_ADMIN_EMAIL = config.get("FIREBASE_ADMIN_EMAIL", "jra@febo.com")
FIREBASE_EMAIL_SENDER = config.get("FIREBASE_EMAIL_SENDER", "jra@febo.com")
SMTP_SERVER = config.get("SMTP_SERVER", "mail-relay.febo.com")
SMTP_PORT = config.get("SMTP_PORT", "587")
SMTP_USERNAME = config.get("SMTP_USERNAME", "jra")

# Function to send email notifications
def send_email_notification(recipient_email, subject, message_html):
    """
    Send an email notification to a user
    
    Args:
        recipient_email (str): The recipient's email address
        subject (str): Email subject line
        message_html (str): HTML content of the email
    
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    try:
        # Create message container
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = FIREBASE_EMAIL_SENDER
        msg['To'] = recipient_email
        msg['Reply-To'] = FIREBASE_ADMIN_EMAIL
        
        # Create the HTML part of the message
        html_part = MIMEText(message_html, 'html')
        msg.attach(html_part)
        
        # Connect to SMTP server and send email
        # Note: Using internal mail relay without authentication
        server = smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT))
        server.ehlo()
        server.starttls()
        server.ehlo()
        # If your mail relay requires login, uncomment the next line
        # server.login(SMTP_USERNAME, SMTP_PASSWORD)
        
        server.sendmail(FIREBASE_EMAIL_SENDER, recipient_email, msg.as_string())
        server.quit()
        
        return True
    except Exception as e:
        st.error(f"Failed to send email: {str(e)}")
        return False

# Function to send approval notification
def send_approval_notification(user_email, role):
    """Send an email notification when a user is approved"""
    app_name = config.get("APP_NAME", "TimeBot")
    app_url = config.get("APP_URL", "https://timebot.febo.com")
    
    subject = f"{app_name} - Your Account Has Been Approved"
    
    # Create HTML message with role-specific information
    role_info = ""
    if role == "premium":
        role_info = "You have been granted <strong>Premium</strong> access with additional features."
    elif role == "admin":
        role_info = "You have been granted <strong>Administrator</strong> privileges."
    else:  # free
        role_info = "You have been granted standard access to the application."
    
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #4CAF50; color: white; padding: 10px; text-align: center; }}
            .content {{ padding: 20px; }}
            .button {{ background-color: #4CAF50; color: white; padding: 10px 20px; 
                      text-decoration: none; border-radius: 4px; display: inline-block; }}
            .footer {{ font-size: 12px; color: #777; margin-top: 30px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>{app_name}</h2>
            </div>
            <div class="content">
                <h3>Good News! Your Account Has Been Approved</h3>
                <p>Your account has been reviewed and approved by our administrators.</p>
                <p>{role_info}</p>
                <p>You can now log in and access the application with your credentials.</p>
                <p>
                    <a href="{app_url}" class="button">Log In Now</a>
                </p>
                <p>If you have any questions or need assistance, please contact our support team.</p>
            </div>
            <div class="footer">
                <p>This is an automated message. Please do not reply to this email.</p>
                <p>&copy; {datetime.now().year} {app_name}. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return send_email_notification(user_email, subject, html_content)

# Function to send rejection notification
def send_rejection_notification(user_email):
    """Send an email notification when a user is rejected"""
    app_name = config.get("APP_NAME", "TimeBot")
    support_email = config.get("SUPPORT_EMAIL", FIREBASE_ADMIN_EMAIL)
    
    subject = f"{app_name} - Account Application Status"
    
    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #f44336; color: white; padding: 10px; text-align: center; }}
            .content {{ padding: 20px; }}
            .footer {{ font-size: 12px; color: #777; margin-top: 30px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>{app_name}</h2>
            </div>
            <div class="content">
                <h3>Account Application Status</h3>
                <p>We have reviewed your account application and unfortunately, we are unable to approve it at this time.</p>
                <p>If you believe this is an error or would like more information, please contact our support team at {support_email}.</p>
            </div>
            <div class="footer">
                <p>This is an automated message. Please do not reply to this email.</p>
                <p>&copy; {datetime.now().year} {app_name}. All rights reserved.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return send_email_notification(user_email, subject, html_content)

# Helper functions for quota management
def get_next_daily_reset():
    """Get timestamp for next daily reset (midnight) in milliseconds"""
    now = datetime.now()
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return int(tomorrow.timestamp() * 1000)

def get_next_monthly_reset():
    """Get timestamp for next monthly reset (1st of next month) in milliseconds"""
    now = datetime.now()
    if now.month == 12:
        next_month = now.replace(
            year=now.year + 1,
            month=1,
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
    else:
        next_month = now.replace(
            month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
        )
    return int(next_month.timestamp() * 1000)

def format_ms_timestamp(ms_timestamp):
    """Format millisecond timestamp to readable date/time"""
    if not ms_timestamp:
        return "N/A"
    dt = datetime.fromtimestamp(ms_timestamp / 1000)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

# Authentication check
def check_password():
    """Returns `True` if the user had the correct password."""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
        
    if st.session_state.password_correct:
        return True
        
    # Create input for password
    st.title("User Approval Dashboard")
    st.write("Please enter the admin password to continue:")
    password = st.text_input("Password", type="password")
    
    # Use the admin password from config
    if password == config.get("ADMIN_DASHBOARD_PASSWORD", "admin123"):
        st.session_state.password_correct = True
        return True
    else:
        if password:
            st.error("😕 Incorrect password")
        return False

if not check_password():
    st.stop()

# Main dashboard
st.title("User Approval Dashboard")

# Define available roles
ROLES = ["free", "premium", "admin"]

# Tabs for different user statuses
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Pending Approvals", "Approved Users", "Rejected Users", "Manage Roles", "Testing", "Quota Management"])

# Function to format timestamp
def format_timestamp(timestamp):
    if timestamp:
        dt = timestamp.astimezone(pytz.timezone('UTC'))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    return "N/A"

# Pending Approvals Tab
with tab1:
    st.header("Pending User Approvals")
    
    # Query users where approved is False or not set
    pending_query = db.collection('users').where('approved', '==', False).stream()
    pending_users = list(pending_query)
    
    if not pending_users:
        st.info("No pending approvals at this time.")
    else:
        st.write(f"Found {len(pending_users)} pending approval(s)")
        
        for user in pending_users:
            user_data = user.to_dict()
            user_id = user.id
            user_email = user_data.get('email', 'No Email')
            
            with st.expander(f"User: {user_email}"):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.write("**User Details:**")
                    st.write(f"- **User ID:** {user_id}")
                    st.write(f"- **Email:** {user_email}")
                    st.write(f"- **Display Name:** {user_data.get('displayName', 'N/A')}")
                    st.write(f"- **Created:** {format_timestamp(user_data.get('createdAt'))}")
                    
                    # Show any additional fields that might be useful
                    additional_fields = {k: v for k, v in user_data.items() 
                                        if k not in ['email', 'displayName', 'createdAt', 'approved']}
                    if additional_fields:
                        st.write("**Additional Information:**")
                        for key, value in additional_fields.items():
                            st.write(f"- **{key}:** {value}")
                    
                    # Add role selection
                    selected_role = st.selectbox(
                        "Select Role", 
                        ROLES, 
                        index=0,  # Default to "free"
                        key=f"role_{user_id}"
                    )
                
                with col2:
                    approve_col, reject_col = st.columns(2)
                    
                    with approve_col:
                        if st.button("Approve", key=f"approve_{user_id}"):
                            # Update user in Firestore with role
                            db.collection('users').document(user_id).update({
                                'approved': True,
                                'approvedAt': firestore.SERVER_TIMESTAMP,
                                'status': 'approved',
                                'role': selected_role
                            })
                            
                            # If role is admin, set custom claim
                            if selected_role == "admin":
                                try:
                                    auth.set_custom_user_claims(user_id, {'admin': True})
                                except Exception as e:
                                    st.error(f"Error setting admin claim: {e}")
                            
                            # Send approval email notification
                            if user_email != 'No Email':
                                email_sent = send_approval_notification(user_email, selected_role)
                                if email_sent:
                                    st.success(f"User approved with role: {selected_role} and notification email sent")
                                else:
                                    st.warning(f"User approved with role: {selected_role} but failed to send notification email")
                            else:
                                st.success(f"User approved with role: {selected_role}")
                            
                            st.rerun()
                    
                    with reject_col:
                        if st.button("Reject", key=f"reject_{user_id}"):
                            # Update user in Firestore
                            db.collection('users').document(user_id).update({
                                'approved': False,
                                'rejectedAt': firestore.SERVER_TIMESTAMP,
                                'status': 'rejected'
                            })
                            
                            # Send rejection email notification
                            if user_email != 'No Email':
                                email_sent = send_rejection_notification(user_email)
                                if email_sent:
                                    st.success("User rejected and notification email sent")
                                else:
                                    st.warning("User rejected but failed to send notification email")
                            else:
                                st.success("User rejected!")
                            
                            st.rerun()

# Approved Users Tab
with tab2:
    st.header("Approved Users")
    
    # Query approved users
    approved_query = db.collection('users').where('approved', '==', True).stream()
    approved_users = list(approved_query)
    
    if not approved_users:
        st.info("No approved users found.")
    else:
        st.write(f"Found {len(approved_users)} approved user(s)")
        
        # Create a table of approved users
        user_data = []
        for user in approved_users:
            data = user.to_dict()
            user_data.append({
                "User ID": user.id,
                "Email": data.get('email', 'N/A'),
                "Display Name": data.get('displayName', 'N/A'),
                "Role": data.get('role', 'free'),
                "Approved At": format_timestamp(data.get('approvedAt')),
            })
        
        st.dataframe(user_data, use_container_width=True)

# Rejected Users Tab
with tab3:
    st.header("Rejected Users")
    
    # Query rejected users (approved=False and status=rejected)
    rejected_query = db.collection('users').where('status', '==', 'rejected').stream()
    rejected_users = list(rejected_query)
    
    if not rejected_users:
        st.info("No rejected users found.")
    else:
        st.write(f"Found {len(rejected_users)} rejected user(s)")
        
        # Create a table of rejected users
        user_data = []
        for user in rejected_users:
            data = user.to_dict()
            user_data.append({
                "User ID": user.id,
                "Email": data.get('email', 'N/A'),
                "Display Name": data.get('displayName', 'N/A'),
                "Rejected At": format_timestamp(data.get('rejectedAt')),
            })
        
        st.dataframe(user_data, use_container_width=True)
        
        # Option to delete rejected users
        if st.button("Delete All Rejected Users", type="primary", use_container_width=True):
            if st.checkbox("I understand this action cannot be undone"):
                for user in rejected_users:
                    db.collection('users').document(user.id).delete()
                st.success("All rejected users have been deleted!")
                st.rerun()
            else:
                st.warning("Please confirm deletion by checking the box")

# Manage Roles Tab
with tab4:
    st.header("Manage User Roles")
    
    # Query all approved users
    users_query = db.collection('users').where('approved', '==', True).stream()
    users = list(users_query)
    
    if not users:
        st.info("No approved users found.")
    else:
        st.write(f"Found {len(users)} approved user(s)")
        
        for user in users:
            user_data = user.to_dict()
            user_id = user.id
            current_role = user_data.get('role', 'free')
            user_email = user_data.get('email', 'No Email')
            
            with st.expander(f"{user_email} - Current Role: {current_role}"):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.write("**User Details:**")
                    st.write(f"- **User ID:** {user_id}")
                    st.write(f"- **Email:** {user_email}")
                    st.write(f"- **Display Name:** {user_data.get('displayName', 'N/A')}")
                    
                    # Role selection
                    new_role = st.selectbox(
                        "Select New Role", 
                        ROLES, 
                        index=ROLES.index(current_role) if current_role in ROLES else 0,
                        key=f"new_role_{user_id}"
                    )
                
                with col2:
                    if st.button("Update Role", key=f"update_role_{user_id}"):
                        # Update user role in Firestore
                        db.collection('users').document(user_id).update({
                            'role': new_role,
                            'roleUpdatedAt': firestore.SERVER_TIMESTAMP
                        })
                        
                        # Handle admin role special case
                        if new_role == "admin":
                            try:
                                auth.set_custom_user_claims(user_id, {'admin': True})
                            except Exception as e:
                                st.error(f"Error setting admin claim: {e}")
                        elif current_role == "admin" and new_role != "admin":
                            try:
                                auth.set_custom_user_claims(user_id, {'admin': False})
                            except Exception as e:
                                st.error(f"Error removing admin claim: {e}")
                        
                        # Send role update notification if role changed
                        if new_role != current_role and user_email != 'No Email':
                            email_sent = send_approval_notification(user_email, new_role)
                            if email_sent:
                                st.success(f"Role updated to: {new_role} and notification email sent")
                            else:
                                st.warning(f"Role updated to: {new_role} but failed to send notification email")
                        else:
                            st.success(f"Role updated to: {new_role}")
                        
                        st.rerun()

# System Tests Tab
with tab5:
    st.header("System Tests")

    # Email Testing Section
    st.subheader("Email Test")

    with st.form("email_test_form"):
        test_email = st.text_input("Recipient Email Address", value=FIREBASE_ADMIN_EMAIL)
        test_role = st.selectbox("Test Role for Approval Email", ROLES, index=0)

        col1, col2 = st.columns(2)
        with col1:
            test_approval_button = st.form_submit_button("Send Test Approval Email")
        with col2:
            test_rejection_button = st.form_submit_button("Send Test Rejection Email")

        if test_approval_button:
            if send_approval_notification(test_email, test_role):
                st.success(f"Test approval email sent successfully to {test_email}")
            else:
                st.error(f"Failed to send test approval email to {test_email}")

        if test_rejection_button:
            if send_rejection_notification(test_email):
                st.success(f"Test rejection email sent successfully to {test_email}")
            else:
                st.error(f"Failed to send test rejection email to {test_email}")

    # Email Configuration Display
    st.subheader("Email Configuration")
    st.json({
        "FIREBASE_ADMIN_EMAIL": FIREBASE_ADMIN_EMAIL,
        "FIREBASE_EMAIL_SENDER": FIREBASE_EMAIL_SENDER,
        "SMTP_SERVER": SMTP_SERVER,
        "SMTP_PORT": SMTP_PORT,
        "SMTP_USERNAME": SMTP_USERNAME,
        "APP_NAME": config.get("APP_NAME", "TimeBot"),
        "APP_URL": config.get("APP_URL", "https://timebot.febo.com"),
        "SUPPORT_EMAIL": config.get("SUPPORT_EMAIL", FIREBASE_ADMIN_EMAIL)
    })

    # Add a section to view email templates
    st.subheader("Email Templates")
    template_tab1, template_tab2 = st.tabs(["Approval Email", "Rejection Email"])

    with template_tab1:
        # Generate a sample approval email for preview
        app_name = config.get("APP_NAME", "TimeBot")
        app_url = config.get("APP_URL", "https://timebot.febo.com")

        role_info = ""
        if test_role == "premium":
            role_info = "You have been granted <strong>Premium</strong> access with additional features."
        elif test_role == "admin":
            role_info = "You have been granted <strong>Administrator</strong> privileges."
        else:  # free
            role_info = "You have been granted standard access to the application."

        approval_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #4CAF50; color: white; padding: 10px; text-align: center; }}
                .content {{ padding: 20px; }}
                .button {{ background-color: #4CAF50; color: white; padding: 10px 20px;
                          text-decoration: none; border-radius: 4px; display: inline-block; }}
                .footer {{ font-size: 12px; color: #777; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>{app_name}</h2>
                </div>
                <div class="content">
                    <h3>Good News! Your Account Has Been Approved</h3>
                    <p>Your account has been reviewed and approved by our administrators.</p>
                    <p>{role_info}</p>
                    <p>You can now log in and access the application with your credentials.</p>
                    <p>
                        <a href="{app_url}" class="button">Log In Now</a>
                    </p>
                    <p>If you have any questions or need assistance, please contact our support team.</p>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                    <p>&copy; {datetime.now().year} {app_name}. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

        st.code(approval_html, language="html")
        st.write("Preview:")
        st.components.v1.html(approval_html, height=600)

    with template_tab2:
        # Generate a sample rejection email for preview
        support_email = config.get("SUPPORT_EMAIL", FIREBASE_ADMIN_EMAIL)

        rejection_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
                .header {{ background-color: #f44336; color: white; padding: 10px; text-align: center; }}
                .content {{ padding: 20px; }}
                .footer {{ font-size: 12px; color: #777; margin-top: 30px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>{app_name}</h2>
                </div>
                <div class="content">
                    <h3>Account Application Status</h3>
                    <p>We have reviewed your account application and unfortunately, we are unable to approve it at this time.</p>
                    <p>If you believe this is an error or would like more information, please contact our support team at {support_email}.</p>
                </div>
                <div class="footer">
                    <p>This is an automated message. Please do not reply to this email.</p>
                    <p>&copy; {datetime.now().year} {app_name}. All rights reserved.</p>
                </div>
            </div>
        </body>
        </html>
        """

        st.code(rejection_html, language="html")
        st.write("Preview:")
        st.components.v1.html(rejection_html, height=400)

    # Add SMTP connection test
    st.subheader("SMTP Connection Test")
    if st.button("Test SMTP Connection"):
        try:
            server = smtplib.SMTP(SMTP_SERVER, int(SMTP_PORT))
            server.ehlo()
            server.starttls()
            server.ehlo()
            # If your mail relay requires login, uncomment the next line
            # server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.quit()
            st.success(f"Successfully connected to SMTP server at {SMTP_SERVER}:{SMTP_PORT}")
        except Exception as e:
            st.error(f"Failed to connect to SMTP server: {str(e)}")

# Quota Management Tab
with tab6:
    st.header("User Quota Management")
    
    # NEW SECTION: Add a section for updating default quotas for all roles
    with st.expander("Update Default Quotas for All User Roles", expanded=True):
        st.write("Set new default quota limits for each user role. This will update all existing users of each role.")
        
        # Create columns for the different roles
        free_col, premium_col, admin_col = st.columns(3)
        
        with free_col:
            st.subheader("Free Users")
            new_free_daily = st.number_input(
                "Daily Limit", 
                min_value=1, 
                value=10,  # Default suggestion
                key="new_free_daily"
            )
            new_free_monthly = st.number_input(
                "Monthly Limit", 
                min_value=1, 
                value=100,  # Default suggestion
                key="new_free_monthly"
            )
        
        with premium_col:
            st.subheader("Premium Users")
            new_premium_daily = st.number_input(
                "Daily Limit", 
                min_value=1, 
                value=50,  # Default suggestion
                key="new_premium_daily"
            )
            new_premium_monthly = st.number_input(
                "Monthly Limit", 
                min_value=1, 
                value=500,  # Default suggestion
                key="new_premium_monthly"
            )
        
        with admin_col:
            st.subheader("Admin Users")
            new_admin_daily = st.number_input(
                "Daily Limit", 
                min_value=1, 
                value=1000,  # Default suggestion
                key="new_admin_daily"
            )
            new_admin_monthly = st.number_input(
                "Monthly Limit", 
                min_value=1, 
                value=10000,  # Default suggestion
                key="new_admin_monthly"
            )
        
        # Add a button to update all users
        if st.button("Update All User Quotas", use_container_width=True):
            try:
                # Get all users
                users_query = db.collection('users').stream()
                users = list(users_query)
                
                # Count of updated users by role
                updated_free = 0
                updated_premium = 0
                updated_admin = 0
                
                # Update each user based on their role
                for user in users:
                    user_data = user.to_dict()
                    user_id = user.id
                    user_role = user_data.get('role', 'free')
                    
                    if user_role == 'free':
                        db.collection('users').document(user_id).update({
                            "limits.google_ai.daily": new_free_daily,
                            "limits.google_ai.monthly": new_free_monthly
                        })
                        updated_free += 1
                    elif user_role == 'premium':
                        db.collection('users').document(user_id).update({
                            "limits.google_ai.daily": new_premium_daily,
                            "limits.google_ai.monthly": new_premium_monthly
                        })
                        updated_premium += 1
                    elif user_role == 'admin':
                        db.collection('users').document(user_id).update({
                            "limits.google_ai.daily": new_admin_daily,
                            "limits.google_ai.monthly": new_admin_monthly
                        })
                        updated_admin += 1
                
                st.success(f"Successfully updated quotas for {len(users)} users: {updated_free} free, {updated_premium} premium, {updated_admin} admin")
                
                # Option to also reset all counters
                if st.checkbox("Also reset all usage counters to zero"):
                    current_time_ms = int(time.time() * 1000)
                    next_daily_reset = get_next_daily_reset()
                    next_monthly_reset = get_next_monthly_reset()
                    
                    for user in users:
                        user_id = user.id
                        db.collection('users').document(user_id).update({
                            "usage.google_ai.daily.count": 0,
                            "usage.google_ai.daily.reset_at": next_daily_reset,
                            "usage.google_ai.monthly.count": 0,
                            "usage.google_ai.monthly.reset_at": next_monthly_reset
                        })
                    
                    st.success(f"Successfully reset usage counters for all {len(users)} users")
                
            except Exception as e:
                st.error(f"Error updating user quotas: {str(e)}")
    
    st.markdown("---")
    
    # EXISTING CODE: Query all users
    all_users_query = db.collection('users').stream()
    all_users = list(all_users_query)
    
    if not all_users:
        st.info("No users found.")
    else:
        st.write(f"Found {len(all_users)} user(s)")
        
        # Create a search box for filtering users
        search_term = st.text_input("Search by email or name", key="quota_search")
        
        # Filter users based on search term
        filtered_users = all_users
        if search_term:
            filtered_users = [
                user for user in all_users 
                if search_term.lower() in user.to_dict().get('email', '').lower() 
                or search_term.lower() in user.to_dict().get('full_name', '').lower()
            ]
            st.write(f"Found {len(filtered_users)} matching user(s)")
        
        # Display user quota information
        for user in filtered_users:
            user_data = user.to_dict()
            user_id = user.id
            user_email = user_data.get('email', 'No Email')
            user_name = user_data.get('full_name', user_data.get('displayName', 'No Name'))
            user_role = user_data.get('role', 'free')
            
            # Get usage data
            usage = user_data.get('usage', {}).get('google_ai', {})
            daily_usage = usage.get('daily', {}).get('count', 0)
            monthly_usage = usage.get('monthly', {}).get('count', 0)
            total_usage = usage.get('total', 0)
            
            # Get limits
            limits = user_data.get('limits', {}).get('google_ai', {})
            daily_limit = limits.get('daily', 0)
            monthly_limit = limits.get('monthly', 0)
            
            # Get reset times
            daily_reset = usage.get('daily', {}).get('reset_at', 0)
            monthly_reset = usage.get('monthly', {}).get('reset_at', 0)
            
            # Convert millisecond timestamps to readable format
            daily_reset_formatted = format_ms_timestamp(daily_reset)
            monthly_reset_formatted = format_ms_timestamp(monthly_reset)
            
            # Calculate current time in milliseconds
            current_time_ms = int(time.time() * 1000)
            
            # Check if reset is due
            daily_reset_due = daily_reset and daily_reset < current_time_ms
            monthly_reset_due = monthly_reset and monthly_reset < current_time_ms
            
            # Create expander for each user
            with st.expander(f"{user_email} - {user_name} ({user_role})"):
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.write("**User Quota Information:**")
                    st.write(f"- **Daily Usage:** {daily_usage} / {daily_limit}")
                    st.write(f"- **Monthly Usage:** {monthly_usage} / {monthly_limit}")
                    st.write(f"- **Total Usage:** {total_usage}")
                    st.write(f"- **Daily Reset At:** {daily_reset_formatted}")
                    st.write(f"- **Monthly Reset At:** {monthly_reset_formatted}")
                    
                    # Show reset status
                    if daily_reset_due:
                        st.warning("⚠️ Daily reset is overdue!")
                    if monthly_reset_due:
                        st.warning("⚠️ Monthly reset is overdue!")
                
                with col2:
                    # Add buttons for quota management
                    if st.button("Reset Daily Quota", key=f"reset_daily_{user_id}"):
                        try:
                            # Update user document
                            db.collection('users').document(user_id).update({
                                "usage.google_ai.daily.count": 0,
                                "usage.google_ai.daily.reset_at": get_next_daily_reset()
                            })
                            st.success("Daily quota reset successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to reset daily quota: {str(e)}")
                    
                    if st.button("Reset Monthly Quota", key=f"reset_monthly_{user_id}"):
                        try:
                            # Update user document
                            db.collection('users').document(user_id).update({
                                "usage.google_ai.monthly.count": 0,
                                "usage.google_ai.monthly.reset_at": get_next_monthly_reset()
                            })
                            st.success("Monthly quota reset successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to reset monthly quota: {str(e)}")
                    
                    if st.button("Reset All Quotas", key=f"reset_all_{user_id}"):
                        try:
                            # Update user document
                            db.collection('users').document(user_id).update({
                                "usage.google_ai.daily.count": 0,
                                "usage.google_ai.daily.reset_at": get_next_daily_reset(),
                                "usage.google_ai.monthly.count": 0,
                                "usage.google_ai.monthly.reset_at": get_next_monthly_reset()
                            })
                            st.success("All quotas reset successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to reset all quotas: {str(e)}")
                
                # Add a section for custom quota adjustment
                st.write("---")
                st.subheader("Custom Quota Adjustment")
                
                col3, col4 = st.columns(2)
                
                with col3:
                    new_daily_limit = st.number_input(
                        "New Daily Limit", 
                        min_value=0, 
                        value=daily_limit,
                        key=f"new_daily_limit_{user_id}"
                    )
                    
                    new_monthly_limit = st.number_input(
                        "New Monthly Limit", 
                        min_value=0, 
                        value=monthly_limit,
                        key=f"new_monthly_limit_{user_id}"
                    )
                
                with col4:
                    if st.button("Update Limits", key=f"update_limits_{user_id}"):
                        try:
                            # Update user document
                            db.collection('users').document(user_id).update({
                                "limits.google_ai.daily": new_daily_limit,
                                "limits.google_ai.monthly": new_monthly_limit
                            })
                            st.success("Quota limits updated successfully!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to update quota limits: {str(e)}")


# Add a refresh button
if st.button("Refresh Data", use_container_width=True):
    st.rerun()

