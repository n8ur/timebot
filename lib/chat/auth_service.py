# /usr/local/lib/timebot/lib/chat/auth_service.py
# Copyright 2025 John Ackermann
# Licensed under the MIT License. See LICENSE.TXT for details.

# auth_service.py - Firebase authentication service for Timebot

import streamlit as st
import pyrebase
import smtplib
import time
import json
import firebase_admin
import uuid
import base64
import logging
from firebase_admin import credentials, firestore
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from shared.config import config

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, config):
        self.config = config
        self.use_auth = config["USE_FIREBASE_AUTH"]

        if self.use_auth:
            self.firebase_config = {
                "apiKey": config["FIREBASE_API_KEY"],
                "authDomain": config["FIREBASE_AUTH_DOMAIN"],
                "databaseURL": config["FIREBASE_DATABASE_URL"],
                "projectId": config["FIREBASE_PROJECT_ID"],
                "storageBucket": config["FIREBASE_STORAGE_BUCKET"],
                "messagingSenderId": config["FIREBASE_MESSAGING_SENDER_ID"],
                "appId": config["FIREBASE_APP_ID"],
            }

            self.firebase = pyrebase.initialize_app(self.firebase_config)
            self.auth_instance = self.firebase.auth()

            # Initialize Firebase Admin SDK for Firestore
            if not firebase_admin._apps:
                cred = credentials.Certificate(
                    config["FIREBASE_SERVICE_ACCOUNT_KEY"]
                )
                firebase_admin.initialize_app(cred)

            # Initialize Firestore client
            self.db = firestore.client()

            # Check for saved authentication
            self._check_saved_auth()
        else:
            self.firebase = None
            self.auth_instance = None
            self.db = None

    def _check_saved_auth(self):
        """Check if there's a saved authentication token and validate it"""
        # First check if we're already authenticated in this session
        if st.session_state.get("authenticated", False):
            return

        # Check for token in URL params
        if "token" in st.query_params:
            token_id = st.query_params["token"]

            try:
                # Look up the token in Firestore
                token_doc = self.db.collection("auth_tokens").document(token_id).get()

                if token_doc.exists:
                    token_data = token_doc.to_dict()

                    # Check if token is expired
                    if token_data.get("expires_at", 0) > time.time():
                        # Token is valid, try to refresh Firebase token
                        try:
                            user = self.auth_instance.refresh(
                                token_data.get("refresh_token")
                            )

                            # Set session state
                            st.session_state.authenticated = True
                            st.session_state.user_id = token_data.get("user_id")
                            st.session_state.user_email = token_data.get("email")
                            st.session_state.auth_token = user["idToken"]
                            st.session_state.refresh_token = user["refreshToken"]

                            # Get user data from Firestore to set full name
                            user_doc = (
                                self.db.collection("users")
                                .document(token_data.get("user_id"))
                                .get()
                            )
                            if user_doc.exists:
                                user_data = user_doc.to_dict()
                                st.session_state.user_full_name = user_data.get(
                                    "full_name", ""
                                )

                            # Update the token in Firestore with new
                            # refresh token
                            self.db.collection("auth_tokens").document(token_id).update(
                                {
                                    "refresh_token": user["refreshToken"],
                                    "last_used_at": time.time(),
                                }
                            )

                            logger.info(
                                f"User auto-logged in via token: "
                                f"{token_data.get('email')}"
                            )

                            # Keep the token in URL for future visits
                            # This is key - we don't clear the token from URL
                        except Exception as e:
                            logger.warning(
                                f"Failed to refresh Firebase token: {str(e)}"
                            )
                            # Delete the invalid token
                            self.db.collection("auth_tokens").document(
                                token_id
                            ).delete()
                            st.query_params.clear()
                    else:
                        # Token expired, delete it
                        self.db.collection("auth_tokens").document(token_id).delete()
                        logger.info(f"Deleted expired auth token: {token_id}")
                        st.query_params.clear()
                else:
                    # Token not found, clear it from URL
                    logger.warning(f"Auth token not found: {token_id}")
                    st.query_params.clear()

                st.rerun()
            except Exception as e:
                logger.error(f"Error checking saved auth: {str(e)}")
                st.query_params.clear()

    def is_authenticated(self):
        """Check if the user is authenticated"""
        if not self.use_auth:
            return True

        return st.session_state.get("authenticated", False)

    def display_auth_ui(self):
        """Display authentication UI with login and signup tabs"""
        if not self.use_auth:
            return

        # Add custom CSS for styling
        st.markdown(
            """
        <style>
        /* Make the tabs look nicer */
        .stTabs [data-baseweb="tab-list"] {
            gap: 5px;
            border-bottom: 1px scolid #ccc;
        }
        
        .stTabs [data-baseweb="tab"] {
            padding: 5px 10px;
            border: 1px solid #ddd;
            border-bottom: none;
            border-radius: 4px 4px 0 0;

            height: auto;
            white-space: pre-wrap;
            border-radius: 4px 4px 0 0;
        }
        
        /* Center the title */
        h1 {
            text-align: center;
            margin-bottom: 2rem;
        }
        </style>
        """,
            unsafe_allow_html=True,
        )

        # Create a centered layout with columns
        _, center_col, _ = st.columns([1, 2, 1])

        with center_col:
            st.title("Timebot Authentication")

            if st.button("About Timebot", use_container_width=True):
                st.query_params["page"] = "info"
                st.rerun()

            st.markdown(
                """
                To create an account, click the **sign up** tab below to enter
                your email address and a password.  Once your account is approved,
                you'll get an email letting you know.  We won't use your
                information for anything other than validating your account.

                **Note:** The timebot server is currently in early testing
                and its performance under load is unknown.  If you have issues
                accessing the system, please let me know (jra at febo dot com)
                what issues you encountered.
                """
            )

            # Check if we need to display the bookmark message
            if st.session_state.get(
                "show_bookmark_message", False
            ) and st.session_state.get("bookmark_url"):
                st.success(
                    f"""
                **For automatic login in the future, bookmark this URL:**
        
                {st.session_state.bookmark_url}
        
                When you want to use Timebot again, use this bookmark
                instead of the regular URL.
                """
                )

                # Clear the flag so the message doesn't show again
                st.session_state.show_bookmark_message = False

                # Add a button to continue
                if st.button("Continue to Timebot"):
                    # Preserve the token in query params
                    if "token" in st.query_params:
                        token = st.query_params["token"]
                        st.query_params.clear()
                        st.query_params["token"] = token
                    st.rerun()

                # Don't show the login/signup UI if we're showing the bookmark message
                return

            auth_tab1, auth_tab2, auth_tab3 = st.tabs(
                ["Login", "Sign Up", "Reset Password"]
            )

            with auth_tab1:
                email = st.text_input("Email", key="login_email")
                password = st.text_input(
                    "Password", type="password", key="login_password"
                )
                remember_me = st.checkbox("Remember me", key="login_remember")

                # Initialize login_in_progress state if it doesn't exist
                if "login_in_progress" not in st.session_state:
                    st.session_state.login_in_progress = False

                if st.button(
                    "Login",
                    use_container_width=True,
                    disabled=st.session_state.login_in_progress,
                ):
                    if not email or not password:
                        st.error("Please enter both email and password")
                    else:
                        try:
                            # Set loading state
                            st.session_state.login_in_progress = True

                            with st.spinner("Logging in..."):
                                user = (
                                    self.auth_instance.sign_in_with_email_and_password(
                                        email, password
                                    )
                                )

                                # Store authentication info in session state
                                st.session_state.authenticated = True
                                st.session_state.user_id = user["localId"]
                                st.session_state.user_email = user["email"]
                                st.session_state.auth_token = user["idToken"]
                                st.session_state.refresh_token = user["refreshToken"]

                                # Get user data from Firestore to set full name
                                user_doc = (
                                    self.db.collection("users")
                                    .document(user["localId"])
                                    .get()
                                )
                                if user_doc.exists:
                                    user_data = user_doc.to_dict()
                                    st.session_state.user_full_name = user_data.get(
                                        "full_name", ""
                                    )

                                # If remember me is checked, create a persistent token
                                if remember_me:
                                    # Generate a unique token ID
                                    token_id = str(uuid.uuid4())

                                    # Calculate expiry (30 days from now)
                                    expiry = time.time() + (
                                        30 * 24 * 60 * 60
                                    )  # 30 days in seconds

                                    # Store token in Firestore
                                    self.db.collection("auth_tokens").document(
                                        token_id
                                    ).set(
                                        {
                                            "user_id": user["localId"],
                                            "email": user["email"],
                                            "refresh_token": user["refreshToken"],
                                            "created_at": time.time(),
                                            "expires_at": expiry,
                                            "last_used_at": time.time(),
                                        }
                                    )

                                    # Set the token in query params for future visits
                                    st.query_params["token"] = token_id

                                    # Display the persistent login URL to the user
                                    base_url = self.config["TIMEBOT_CHAT_BASE_URL"]
                                    if base_url.endswith("/"):
                                        base_url = base_url[:-1]
                                    persistent_url = f"{base_url}?token={token_id}"

                                    # store URL in session state to display after rerun
                                    st.session_state.show_bookmark_message = True
                                    st.session_state.bookmark_url = persistent_url

                                    logger.info(
                                        f"Created persistent token for: {email}"
                                    )

                                logger.info(f"User logged in: {email}")

                            # Reset loading state
                            st.session_state.login_in_progress = False

                            # Only rerun if we're not showing the bookmark message
                            if not (
                                remember_me
                                and st.session_state.get("show_bookmark_message", False)
                            ):
                                st.rerun()
                        except Exception as e:
                            # Reset loading state
                            st.session_state.login_in_progress = False

                            error_message_str = str(e)
                            user_friendly_message = (
                                "Authentication failed. Please try again."
                            )

                            # Check for specific, common errors and log concisely
                            if "INVALID_LOGIN_CREDENTIALS" in error_message_str:
                                user_friendly_message = (
                                    "Invalid email or password. Please try again."
                                )
                                # Log CONCISE message for this common error
                                logger.warning(
                                    f"Login failed for {email}: Invalid credentials."
                                )
                            elif "TOO_MANY_ATTEMPTS_TRY_LATER" in error_message_str:
                                user_friendly_message = (
                                    "Too many failed login attempts. Please try later."
                                )
                                # Log CONCISE message for this common error
                                logger.warning(
                                    f"Login failed for {email}: Too many attempts."
                                )
                            elif "INVALID_EMAIL" in error_message_str:
                                user_friendly_message = "Invalid email address."
                                # Log CONCISE message for this common error
                                logger.warning(f"Invalid email address: {email}")
                            elif "EMAIL_EXISTS" in error_message_str:
                                user_friendly_message = "Email exists."
                                # Log CONCISE message for this common error
                                logger.warning(f"Duplicate email address: {email}")


                            # Handle unexpected errors
                            else:
                                # For any other exception, log FULL details
                                user_friendly_message = (
                                    "An unexpected error occurred during login."
                                )
                                logger.warning(
                                    f"Unexpected login error for {email}:"
                                    f" {error_message_str}"
                                )

                            # Display user-friendly message regardless of type
                            st.error(user_friendly_message)

            with auth_tab2:
                full_name = st.text_input("User Name", key="signup_full_name")
                email = st.text_input("Email", key="signup_email")
                password = st.text_input(
                    "Password", type="password", key="signup_password"
                )
                confirm_password = st.text_input("Confirm Password", type="password")

                # Initialize signup_in_progress state if it doesn't exist
                if "signup_in_progress" not in st.session_state:
                    st.session_state.signup_in_progress = False

                if st.button(
                    "Sign Up",
                    use_container_width=True,
                    disabled=st.session_state.signup_in_progress,
                ):
                    if (
                        not full_name
                        or not email
                        or not password
                        or not confirm_password
                    ):
                        st.error("Please fill in all fields")
                    elif password != confirm_password:
                        st.error("Passwords don't match")
                    else:
                        try:
                            # Set loading state
                            st.session_state.signup_in_progress = True

                            with st.spinner("Creating account..."):
                                user = self.auth_instance.create_user_with_email_and_password(
                                    email, password
                                )

                                # Get current timestamp in milliseconds
                                current_time = int(time.time() * 1000)

                                # Calculate reset times
                                daily_reset = self._get_next_daily_reset()
                                monthly_reset = self._get_next_monthly_reset()

                                # Create entry in Firestore with extended user data
                                self.db.collection("users").document(
                                    user["localId"]
                                ).set(
                                    {
                                        "email": email,
                                        "full_name": full_name,
                                        "approved": False,
                                        "created_at": current_time,
                                        "role": "free",  # Default role
                                        "usage": {
                                            "google_ai": {
                                                "daily": {
                                                    "count": 0,
                                                    "reset_at": daily_reset,
                                                },
                                                "monthly": {
                                                    "count": 0,
                                                    "reset_at": monthly_reset,
                                                },
                                                "total": 0,
                                                "last_used_at": 0,
                                            }
                                        },
                                        "limits": {
                                            "google_ai": {
                                                "daily": self.config["FREE_DAILY_LIMIT"],
                                                "monthly": self.config["FREE_MONTHLY_LIMIT"],
                                            }
                                        },
                                    }
                                )

                                # Send notification email with full name included
                                self.send_approval_email(
                                    user["localId"], email, full_name
                                )

                                st.success(
                                    "Account created! Waiting for admin approval."
                                )
                                logger.info(f"New user signup: {full_name} ({email})")

                            # Reset loading state
                            st.session_state.signup_in_progress = False

                        except Exception as e:
                            # Reset loading state
                            st.session_state.signup_in_progress = False

                            error_message = str(e)
                            if "EMAIL_EXISTS" in error_message:
                                error_message = """
                                    An account with this email already exists.
                                    Please use a different email or try to
                                    reset your password.
                                    """
                            elif "WEAK_PASSWORD" in error_message:
                                error_message = (
                                    "Password is too weak. Please use a stronger one."
                                )
                            elif "INVALID_EMAIL" in error_message:
                                error_message = """
                                    Invalid email format. Please enter a valid
                                    email address.
                                    """

                            logger.warning(f"Signup failed for {email}: {str(e)}")
                            st.error(f"Signup failed: {error_message}")

            with auth_tab3:
                # Widget is instantiated here, linked to st.session_state.reset_email
                reset_email_input = st.text_input("Email", key="reset_email")

                # Initialize reset_in_progress and reset_success states
                # if they don't exist
                if "reset_in_progress" not in st.session_state:
                    st.session_state.reset_in_progress = False
                if "reset_success" not in st.session_state:
                    st.session_state.reset_success = False

                if st.session_state.reset_success:
                    # Read the value directly from session state
                    # (it was set by the widget)
                    st.success(
                        f"Password reset email sent to {st.session_state.reset_email}."
                        f" Please check your inbox and follow the instructions"
                        f" to reset your password."
                    )

                    # Add a button to return to login
                    if st.button("Return to Login"):
                        st.session_state.reset_success = False
                        # REMOVED: st.session_state.reset_email = ""
                        # Rerun will cause the input field to show again
                        st.rerun()
                else:
                    if st.button(
                        "Send Reset Link",
                        use_container_width=True,
                        disabled=st.session_state.reset_in_progress,
                    ):
                        # Read the value from st.text_input OR from
                        # st.session_state.reset_email
                        if not reset_email_input:
                            st.error("Please enter your email address")
                        else:
                            try:
                                # Set loading state
                                st.session_state.reset_in_progress = True

                                with st.spinner("Sending password reset email..."):
                                    # Use the value read from the input
                                    self.auth_instance.send_password_reset_email(
                                        reset_email_input
                                    )
                                    # Store the success state for the next run
                                    st.session_state.reset_success = True
                                    logger.info(
                                        f"Password reset requested for: "
                                        f"{reset_email_input}"
                                    )

                                # Reset loading state
                                st.session_state.reset_in_progress = False

                                # Rerun to show success message and return button
                                st.rerun()

                            except Exception as e:
                                # Reset loading state
                                st.session_state.reset_in_progress = False

                                error_message = str(e)
                                if "EMAIL_NOT_FOUND" in error_message:
                                    error_message = (
                                        "No account found with this email address."
                                    )

                                # Log using the email from the input
                                logger.warning(
                                    f"Password reset failed for "
                                    f"{reset_email_input}: {str(e)}"
                                )
                                st.error(f"Failed to send reset email: {error_message}")

    def check_user_approval(self, user_id):
        """Check if user has been approved by admin"""
        if not self.use_auth:
            return True

        try:
            user_doc = self.db.collection("users").document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                return user_data.get("approved", False)
            return False
        except Exception as e:
            logger.error(f"Error checking user approval: {str(e)}")
            return False

    def send_approval_email(self, user_id, user_email, full_name=""):
        """Send email notification to admin for approval"""
        if not self.use_auth:
            return

        try:
            admin_email = self.config["FIREBASE_ADMIN_EMAIL"]
            sender = self.config["FIREBASE_EMAIL_SENDER"]

            # Include full name in the email body
            email_body = (
                f"New user signup request:\n"
                f"User ID: {user_id}\nName: {full_name}\n"
                f"Email: {user_email}"
            )

            msg = MIMEText(email_body)
            msg["Subject"] = "Timebot: New User Approval Request"
            msg["From"] = sender
            msg["To"] = admin_email

            # Configure SMTP server details from config
            smtp_server = smtplib.SMTP(
                self.config["SMTP_SERVER"], self.config["SMTP_PORT"]
            )
            smtp_server.starttls()
            # smtp_server.login(
            #    self.config.get("SMTP_USERNAME"),
            #    self.config.get("SMTP_PASSWORD", "")
            # )
            smtp_server.send_message(msg)
            smtp_server.quit()

            logger.info(f"Approval email sent for user: {full_name} ({user_email})")
        except Exception as e:
            logger.error(f"Failed to send approval email: {str(e)}")

    def display_logout_button(self):
        """Display logout button in sidebar"""
        if not self.use_auth:
            return

        # Display user info in sidebar
        if st.session_state.get("user_full_name"):
            st.sidebar.write(f"Logged in as: **{st.session_state.user_full_name}**")
        else:
            st.sidebar.write(f"Logged in as: **{st.session_state.user_email}**")

        if st.sidebar.button("Logout"):
            # Clear persistent token if it exists
            if "token" in st.query_params:
                token_id = st.query_params["token"]
                try:
                    # Delete the token from Firestore
                    self.db.collection("auth_tokens").document(token_id).delete()
                    logger.info(f"Deleted auth token on logout: {token_id}")
                except Exception as e:
                    logger.error(f"Error deleting auth token: {str(e)}")

            # Clear session state
            st.session_state.authenticated = False
            st.session_state.user_id = None
            st.session_state.user_email = None
            st.session_state.user_full_name = None
            st.session_state.auth_token = None
            st.session_state.refresh_token = None

            # Clear query params
            st.query_params.clear()

            logger.info(
                f"User logged out: {st.session_state.get('user_email', 'Unknown')}"
            )
            st.rerun()

    def auth_required(self, func):
        """Decorator to require authentication before running a function"""

        def wrapper(*args, **kwargs):
            if not self.use_auth:
                return func(*args, **kwargs)

            current_page = st.query_params.get("page", "main")
            if current_page == "info":
                return func(*args, **kwargs)

            if "authenticated" not in st.session_state:
                st.session_state.authenticated = False

            if not st.session_state.authenticated:
                # save current query params before showing auth ui
                current_page = st.query_params.get("page", "main")
                current_token = st.query_params.get("token", None)

                # display auth ui
                self.display_auth_ui()

                # if authentication was successful in this run, restore the page
                if st.session_state.get("authenticated", False):
                    # Set the page query param
                    st.query_params["page"] = current_page

                    # If we had a token and it wasn't preserved
                    # (e.g., not using remember me), restore it
                    if current_token and "token" not in st.query_params:
                        st.query_params["token"] = current_token

                    st.rerun()
                return None

            # If we're showing the bookmark message, display the auth UI and return
            if st.session_state.get("show_bookmark_message", False):
                self.display_auth_ui()
                return None

            if not self.check_user_approval(st.session_state.user_id):
                st.warning(
                    "Your account is pending approval. "
                    "You'll be notified when it's approved."
                )
                if st.button("Logout"):
                    st.session_state.authenticated = False
                    st.session_state.user_id = None
                    st.session_state.user_email = None
                    st.session_state.user_full_name = None
                    st.session_state.auth_token = None
                    st.session_state.refresh_token = None

                    # Clear query params
                    st.query_params.clear()

                    st.rerun()
                return None

            # display logout button in sidebar
            self.display_logout_button()

            # run the wrapped function
            return func(*args, **kwargs)

        return wrapper

    def _get_next_daily_reset(self):
        """Get timestamp for next daily reset (midnight)"""

        now = datetime.now()
        tomorrow = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        return int(tomorrow.timestamp() * 1000)

    def _get_next_monthly_reset(self):
        """Get timestamp for next monthly reset (1st of next month)"""

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

    def update_user_role(self, user_id, role):
        """Update user role and set appropriate limits"""
        if not self.use_auth:
            return

        try:
            # Get the appropriate limits based on role
            if role == "premium":
                daily_limit = self.config["PREMIUM_DAILY_LIMIT"]
                monthly_limit = self.config["PREMIUM_MONTHLY_LIMIT"]
            elif role == "admin":
                daily_limit = self.config["ADMIN_DAILY_LIMIT"]
                monthly_limit = self.config["ADMIN_MONTHLY_LIMIT"]
            else:  # Default to free
                daily_limit = self.config["FREE_DAILY_LIMIT"]
                monthly_limit = self.config["FREE_MONTHLY_LIMIT"]

            # Update user document in Firestore
            self.db.collection("users").document(user_id).update(
                {
                    "role": role,
                    "limits.google_ai.daily": daily_limit,
                    "limits.google_ai.monthly": monthly_limit,
                }
            )

            logger.info(
                f"Updated user {user_id} to role: {role} "
                f"with limits: daily={daily_limit}, monthly={monthly_limit}"
            )
            return True
        except Exception as e:
            logger.error(f"Error updating user role: {str(e)}")
            return False

    def get_user_role(self, user_id):
        """Get the user's current role"""
        if not self.use_auth:
            return "admin"  # Default to admin when auth is disabled

        try:
            user_doc = self.db.collection("users").document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                return user_data.get("role", "free")
            return "free"  # Default to free if user document doesn't exist
        except Exception as e:
            logger.error(f"Error getting user role: {str(e)}")
            return "free"  # Default to free on error

    def get_user_limits(self, user_id):
        """Get the user's current usage limits"""
        if not self.use_auth:
            return {"daily": self.config["ADMIN_DAILY_LIMIT"], "monthly": self.config["ADMIN_MONTHLY_LIMIT"]}

        try:
            user_doc = self.db.collection("users").document(user_id).get()
            if user_doc.exists:
                user_data = user_doc.to_dict()
                limits = user_data.get("limits", {}).get("google_ai", {})
                return {
                    "daily": limits.get("daily", self.config["FREE_DAILY_LIMIT"]),
                    "monthly": limits.get("monthly", self.config["FREE_MONTHLY_LIMIT"]),
                }
            return {"daily": self.config["FREE_DAILY_LIMIT"], "monthly": self.config["FREE_MONTHLY_LIMIT"]}
        except Exception as e:
            logger.error(f"Error getting user limits: {str(e)}")
            return {"daily": self.config["FREE_DAILY_LIMIT"], "monthly": self.config["FREE_MONTHLY_LIMIT"]}
