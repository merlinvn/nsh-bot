"""Script to generate PKCE code_verifier and code_challenge for Zalo OAuth.

Run this script to generate a new PKCE pair, then:
1. Add ZALO_CODE_VERIFIER=<code_verifier> to your .env file
2. Register the code_challenge in Zalo Developer Portal

Usage:
    python -m app.api.scripts.generate_pkce
"""
import argparse
import base64
import hashlib
import secrets


def generate_code_verifier() -> str:
    """Generate a random code verifier for PKCE (43 characters)."""
    return secrets.token_urlsafe(43)[:43]


def generate_code_challenge(code_verifier: str) -> str:
    """Generate code challenge from code verifier using SHA-256 + Base64."""
    sha256_hash = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(sha256_hash).rstrip(b"=").decode("ascii")


def main():
    parser = argparse.ArgumentParser(description="Generate PKCE code_verifier and code_challenge for Zalo OAuth")
    parser.add_argument(
        "--register",
        action="store_true",
        help="Also add the code_verifier to .env file",
    )
    args = parser.parse_args()

    code_verifier = generate_code_verifier()
    code_challenge = generate_code_challenge(code_verifier)

    print("=" * 60)
    print("PKCE Code Verifier and Challenge for Zalo OAuth")
    print("=" * 60)
    print()
    print("CODE_VERIFIER (add to .env as ZALO_CODE_VERIFIER):")
    print(f"  {code_verifier}")
    print()
    print("CODE_CHALLENGE (register in Zalo Developer Portal):")
    print(f"  {code_challenge}")
    print()
    print("=" * 60)
    print()
    print("Next steps:")
    print("1. Add the CODE_VERIFIER to your .env file:")
    print(f"   echo 'ZALO_CODE_VERIFIER={code_verifier}' >> .env")
    print()
    print("2. Register CODE_CHALLENGE in Zalo Developer Portal")
    print("   (set callback URL and code_challenge in your app settings)")
    print()
    print("3. Restart the API and visit /auth/zalo/login")
    print("=" * 60)

    if args.register:
        env_path = ".env"
        try:
            with open(env_path, "r") as f:
                content = f.read()
        except FileNotFoundError:
            content = ""

        # Check if ZALO_CODE_VERIFIER already exists
        if "ZALO_CODE_VERIFIER=" in content:
            # Replace existing
            import re
            content = re.sub(r"ZALO_CODE_VERIFIER=.*", f"ZALO_CODE_VERIFIER={code_verifier}", content)
        else:
            content += f"\nZALO_CODE_VERIFIER={code_verifier}\n"

        with open(env_path, "w") as f:
            f.write(content)
        print(f"\nAdded ZALO_CODE_VERIFIER to {env_path}")


if __name__ == "__main__":
    main()
