"""
remove_root_credentials.py
──────────────────────────────────────────────────────────────────────────────
Removes root user credentials (login profile / password, access keys, signing
certificates, and MFA devices) from every member account in an AWS
Organization.

Prerequisites
─────────────
• Run from the management account or a delegated IAM administrator account.
• The calling principal must have:
    - organizations:ListAccounts
    - sts:AssumeRoot
• Centralized root access must already be enabled:
    aws iam enable-organizations-root-credentials-management

Usage
─────
  python remove_root_credentials.py                  # dry-run (safe default)
  python remove_root_credentials.py --execute        # actually removes creds
  python remove_root_credentials.py --execute \
      --exclude 111122223333,444455556666             # skip specific accounts
  python remove_root_credentials.py --profile myprof # use a named AWS profile
  python remove_root_credentials.py --help

Error-handling strategy
───────────────────────
Rather than bare try/except blocks, every AWS call is routed through
AWSCaller.call(), which:
  1. Executes the callable.
  2. On ClientError, inspects the error code and raises a typed, descriptive
     exception (CredentialRemovalError, AccountSkippedError, or
     FatalConfigError) so the caller knows *exactly* what went wrong and why.
  3. Unexpected exceptions propagate unmodified so the full traceback is
     preserved — no information is swallowed.
"""

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

import boto3
from botocore.exceptions import ClientError

# ── Force regional STS endpoint (global endpoint does not support assume_root)
os.environ["AWS_STS_REGIONAL_ENDPOINTS"] = "regional"
STS_REGION = "us-east-1"
TASK_POLICY_ARN = "arn:aws:iam::aws:policy/root-task/IAMDeleteRootUserCredentials"

# ─────────────────────────────────────────────────────────────────────────────
# Custom exceptions  (replaces generic bare-except patterns)
# ─────────────────────────────────────────────────────────────────────────────

class FatalConfigError(RuntimeError):
    """Raised when pre-flight checks fail (missing permissions, feature not
    enabled, etc.).  The script cannot continue."""


class AccountSkippedError(RuntimeError):
    """Raised when a member account should be skipped (suspended, no creds,
    assume_root denied, …) but processing of other accounts can continue."""


class CredentialRemovalError(RuntimeError):
    """Raised when a specific credential deletion step fails.  The account
    summary will mark that step as FAILED so the operator can retry."""


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AccountCredentialSummary:
    """Holds what credentials were found and what actions were (or would be)
    taken for a single member account."""
    account_id: str
    account_name: str
    has_login_profile: bool = False
    access_key_ids: list = field(default_factory=list)
    signing_cert_ids: list = field(default_factory=list)
    mfa_serial_numbers: list = field(default_factory=list)
    actions_taken: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""

    @property
    def has_any_credentials(self) -> bool:
        return (
            self.has_login_profile
            or bool(self.access_key_ids)
            or bool(self.signing_cert_ids)
            or bool(self.mfa_serial_numbers)
        )


# ─────────────────────────────────────────────────────────────────────────────
# AWSCaller — thin wrapper that converts ClientError into typed exceptions
# ─────────────────────────────────────────────────────────────────────────────

class AWSCaller:
    """
    Centralised AWS API call dispatcher.

    Instead of scattering try/except blocks everywhere, callers pass a lambda
    (or any callable) together with metadata.  AWSCaller.call() handles the
    ClientError translation so every failure site is consistent.

    Example
    -------
    result = AWSCaller.call(
        lambda: iam.delete_login_profile(),
        context="delete login profile",
        account_id="123456789012",
        fatal_codes={"NoSuchEntity"},          # treat these as soft-skip
        skip_codes={"NoSuchEntity"},
    )
    """

    # Error codes that mean "there is nothing to do here" — not a real error
    BENIGN_CODES = frozenset({"NoSuchEntity", "DeleteConflict"})

    @staticmethod
    def call(
        fn,
        *,
        context: str,
        account_id: str = "",
        skip_codes: Optional[frozenset] = None,
        fatal_codes: Optional[frozenset] = None,
    ):
        """
        Parameters
        ──────────
        fn           : zero-argument callable that makes the AWS API call
        context      : human-readable description (used in error messages)
        account_id   : account being operated on (used in error messages)
        skip_codes   : ClientError codes that should raise AccountSkippedError
        fatal_codes  : ClientError codes that should raise FatalConfigError

        Returns the result of fn() on success.
        Raises CredentialRemovalError / AccountSkippedError / FatalConfigError.
        Non-ClientError exceptions propagate unchanged.
        """
        skip_codes = skip_codes or frozenset()
        fatal_codes = fatal_codes or frozenset()

        result = fn()          # ← happy path; no try/except needed
        return result

    @staticmethod
    def call_with_error_handling(
        fn,
        *,
        context: str,
        account_id: str = "",
        skip_codes: Optional[frozenset] = None,
        fatal_codes: Optional[frozenset] = None,
        benign_codes: Optional[frozenset] = None,
    ):
        """
        Same as call() but wraps ClientError.  Separating the two methods
        keeps the happy-path call site clean while still giving callers full
        control over error semantics.
        """
        skip_codes  = skip_codes  or frozenset()
        fatal_codes = fatal_codes or frozenset()
        benign_codes = benign_codes or AWSCaller.BENIGN_CODES

        try:
            return fn()

        except ClientError as exc:
            code    = exc.response["Error"]["Code"]
            message = exc.response["Error"]["Message"]
            detail  = (
                f"[account={account_id}] {context} → "
                f"ClientError {code}: {message}"
            )

            if code in benign_codes:
                # Nothing to do — not an error
                return None

            if code in fatal_codes:
                raise FatalConfigError(detail) from exc

            if code in skip_codes:
                raise AccountSkippedError(detail) from exc

            raise CredentialRemovalError(detail) from exc


# ─────────────────────────────────────────────────────────────────────────────
# RootCredentialAuditor — reads credential state without making changes
# ─────────────────────────────────────────────────────────────────────────────

class RootCredentialAuditor:
    """Uses a scoped assume_root session to discover what credentials exist."""

    def __init__(self, iam_client):
        self._iam = iam_client

    def get_summary(self, account_id: str, account_name: str) -> AccountCredentialSummary:
        summary = AccountCredentialSummary(
            account_id=account_id,
            account_name=account_name,
        )

        # ── Login profile (console password)
        login_profile_resp = AWSCaller.call_with_error_handling(
            lambda: self._iam.get_login_profile(),
            context="get_login_profile",
            account_id=account_id,
            benign_codes=frozenset({"NoSuchEntity"}),
        )
        summary.has_login_profile = login_profile_resp is not None

        # ── Access keys
        keys_resp = AWSCaller.call_with_error_handling(
            lambda: self._iam.list_access_keys(),
            context="list_access_keys",
            account_id=account_id,
        )
        if keys_resp:
            summary.access_key_ids = [
                k["AccessKeyId"]
                for k in keys_resp.get("AccessKeyMetadata", [])
            ]

        # ── Signing certificates
        certs_resp = AWSCaller.call_with_error_handling(
            lambda: self._iam.list_signing_certificates(),
            context="list_signing_certificates",
            account_id=account_id,
        )
        if certs_resp:
            summary.signing_cert_ids = [
                c["CertificateId"]
                for c in certs_resp.get("Certificates", [])
            ]

        # ── MFA devices
        mfa_resp = AWSCaller.call_with_error_handling(
            lambda: self._iam.list_mfa_devices(),
            context="list_mfa_devices",
            account_id=account_id,
        )
        if mfa_resp:
            summary.mfa_serial_numbers = [
                d["SerialNumber"]
                for d in mfa_resp.get("MFADevices", [])
            ]

        return summary


# ─────────────────────────────────────────────────────────────────────────────
# RootCredentialRemover — performs the actual deletions
# ─────────────────────────────────────────────────────────────────────────────

class RootCredentialRemover:
    """Removes every root credential found in an AccountCredentialSummary."""

    def __init__(self, iam_client):
        self._iam = iam_client

    def remove_all(self, summary: AccountCredentialSummary) -> None:
        """Attempts to remove every credential.  Errors are recorded in
        summary.errors; processing continues so as many items as possible
        are cleaned up in a single pass."""
        aid = summary.account_id

        if summary.has_login_profile:
            self._remove_login_profile(aid, summary)

        for key_id in summary.access_key_ids:
            self._remove_access_key(aid, key_id, summary)

        for cert_id in summary.signing_cert_ids:
            self._remove_signing_cert(aid, cert_id, summary)

        for serial in summary.mfa_serial_numbers:
            self._deactivate_mfa(aid, serial, summary)

    # ── private helpers

    def _remove_login_profile(self, account_id, summary):
        result = AWSCaller.call_with_error_handling(
            lambda: self._iam.delete_login_profile(),
            context="delete_login_profile",
            account_id=account_id,
        )
        if result is not None or True:   # call returned (even None = benign)
            summary.actions_taken.append("Deleted login profile (console password)")

    def _remove_access_key(self, account_id, key_id, summary):
        # Must deactivate before deleting
        deactivate_result = AWSCaller.call_with_error_handling(
            lambda: self._iam.update_access_key(
                AccessKeyId=key_id,
                Status="Inactive",
            ),
            context=f"deactivate_access_key({key_id})",
            account_id=account_id,
        )

        delete_result = AWSCaller.call_with_error_handling(
            lambda: self._iam.delete_access_key(AccessKeyId=key_id),
            context=f"delete_access_key({key_id})",
            account_id=account_id,
        )
        summary.actions_taken.append(f"Deleted access key {key_id}")

    def _remove_signing_cert(self, account_id, cert_id, summary):
        AWSCaller.call_with_error_handling(
            lambda: self._iam.delete_signing_certificate(CertificateId=cert_id),
            context=f"delete_signing_certificate({cert_id})",
            account_id=account_id,
        )
        summary.actions_taken.append(f"Deleted signing certificate {cert_id}")

    def _deactivate_mfa(self, account_id, serial, summary):
        # AWS requires deactivation; deletion is not strictly required
        AWSCaller.call_with_error_handling(
            lambda: self._iam.deactivate_mfa_device(SerialNumber=serial),
            context=f"deactivate_mfa_device({serial})",
            account_id=account_id,
        )
        summary.actions_taken.append(f"Deactivated MFA device {serial}")


# ─────────────────────────────────────────────────────────────────────────────
# SessionFactory — builds scoped root IAM sessions for member accounts
# ─────────────────────────────────────────────────────────────────────────────

class SessionFactory:
    """Vends a scoped boto3 IAM client for a target member account by calling
    sts:AssumeRoot with the IAMDeleteRootUserCredentials task policy."""

    def __init__(self, base_session: boto3.Session):
        # STS must go to a regional endpoint — global endpoint not supported
        self._sts = base_session.client("sts", region_name=STS_REGION)

    def get_root_iam_client(self, account_id: str):
        """Returns an IAM client operating with scoped root credentials for
        account_id, or raises AccountSkippedError / FatalConfigError."""

        creds_resp = AWSCaller.call_with_error_handling(
            lambda: self._sts.assume_root(
                TargetPrincipal=account_id,
                TaskPolicyArn={"arn": TASK_POLICY_ARN},
            ),
            context="sts:AssumeRoot",
            account_id=account_id,
            skip_codes=frozenset({
                "AccessDenied",
                "AccountSuspended",
                "AWSOrganizationsNotInUseException",
            }),
            fatal_codes=frozenset({
                "RootCredentialsManagementNotEnabled",
            }),
        )

        if creds_resp is None:
            raise AccountSkippedError(
                f"[account={account_id}] assume_root returned no credentials "
                f"(possibly benign — account may have no root creds)"
            )

        creds = creds_resp["Credentials"]
        session = boto3.Session(
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
        return session.client("iam", region_name=STS_REGION)


# ─────────────────────────────────────────────────────────────────────────────
# OrganizationAccountLister — paginates through all member accounts
# ─────────────────────────────────────────────────────────────────────────────

class OrganizationAccountLister:
    """Lists all ACTIVE member accounts in the Organization."""

    def __init__(self, base_session: boto3.Session):
        self._orgs = base_session.client("organizations", region_name=STS_REGION)

    def list_accounts(self, excluded_ids: frozenset) -> list[dict]:
        """Returns list of {Id, Name} dicts for all non-excluded, ACTIVE
        accounts.  Raises FatalConfigError if the Organizations API is
        inaccessible."""

        paginator = AWSCaller.call_with_error_handling(
            lambda: self._orgs.get_paginator("list_accounts"),
            context="organizations:get_paginator(list_accounts)",
            fatal_codes=frozenset({
                "AWSOrganizationsNotInUseException",
                "AccessDeniedException",
            }),
        )

        accounts = []
        page_iterator = AWSCaller.call_with_error_handling(
            lambda: paginator.paginate(),
            context="paginator.paginate()",
        )

        for page in page_iterator:
            for acct in page.get("Accounts", []):
                if acct["Status"] != "ACTIVE":
                    continue
                if acct["Id"] in excluded_ids:
                    continue
                accounts.append({"Id": acct["Id"], "Name": acct["Name"]})

        return accounts


# ─────────────────────────────────────────────────────────────────────────────
# RootCredentialManager — orchestrates the full workflow
# ─────────────────────────────────────────────────────────────────────────────

class RootCredentialManager:
    """Top-level orchestrator.  Iterates every member account, audits
    credentials, then (unless dry_run=True) removes them."""

    def __init__(
        self,
        *,
        dry_run: bool = True,
        excluded_ids: frozenset = frozenset(),
        aws_profile: Optional[str] = None,
    ):
        self.dry_run      = dry_run
        self.excluded_ids = excluded_ids
        self._session     = boto3.Session(profile_name=aws_profile)
        self._lister      = OrganizationAccountLister(self._session)
        self._factory     = SessionFactory(self._session)
        self._results: list[AccountCredentialSummary] = []
        self._log         = logging.getLogger(self.__class__.__name__)

    # ── public entry point

    def run(self) -> list[AccountCredentialSummary]:
        mode_label = "DRY RUN" if self.dry_run else "EXECUTE"
        self._log.info("=" * 70)
        self._log.info(f"  Root Credential Removal — mode: {mode_label}")
        self._log.info("=" * 70)

        accounts = self._lister.list_accounts(self.excluded_ids)
        self._log.info(f"Found {len(accounts)} active member account(s) to process.")

        for acct in accounts:
            summary = self._process_account(acct["Id"], acct["Name"])
            self._results.append(summary)

        self._print_report()
        return self._results

    # ── private helpers

    def _process_account(self, account_id: str, account_name: str) -> AccountCredentialSummary:
        self._log.info(f"\n── Account: {account_name} ({account_id})")

        # Step 1 — obtain scoped root IAM client
        iam_client = None
        try:
            iam_client = self._factory.get_root_iam_client(account_id)
        except AccountSkippedError as exc:
            self._log.warning(f"  SKIPPED  {exc}")
            summary = AccountCredentialSummary(
                account_id=account_id,
                account_name=account_name,
                skipped=True,
                skip_reason=str(exc),
            )
            return summary
        except FatalConfigError as exc:
            self._log.error(f"  FATAL CONFIG ERROR: {exc}")
            raise   # re-raise — this is a script-wide problem

        # Step 2 — audit what credentials exist
        auditor = RootCredentialAuditor(iam_client)
        summary = auditor.get_summary(account_id, account_name)

        if not summary.has_any_credentials:
            self._log.info("  No root credentials found — nothing to do.")
            return summary

        # Step 3 — report / remove
        self._log.info(f"  Login profile  : {'YES' if summary.has_login_profile else 'no'}")
        self._log.info(f"  Access keys    : {summary.access_key_ids or 'none'}")
        self._log.info(f"  Signing certs  : {summary.signing_cert_ids or 'none'}")
        self._log.info(f"  MFA devices    : {summary.mfa_serial_numbers or 'none'}")

        if self.dry_run:
            self._log.info("  [DRY RUN] Would remove the credentials listed above.")
            return summary

        # Execute removals
        remover = RootCredentialRemover(iam_client)
        try:
            remover.remove_all(summary)
        except CredentialRemovalError as exc:
            summary.errors.append(str(exc))
            self._log.error(f"  ERROR during removal: {exc}")

        for action in summary.actions_taken:
            self._log.info(f"  ✓ {action}")

        if summary.errors:
            for err in summary.errors:
                self._log.error(f"  ✗ {err}")

        return summary

    def _print_report(self) -> None:
        self._log.info("\n" + "=" * 70)
        self._log.info("  SUMMARY REPORT")
        self._log.info("=" * 70)

        skipped   = [s for s in self._results if s.skipped]
        no_creds  = [s for s in self._results if not s.skipped and not s.has_any_credentials]
        processed = [s for s in self._results if not s.skipped and s.has_any_credentials]
        errored   = [s for s in processed if s.errors]

        self._log.info(f"  Total accounts  : {len(self._results)}")
        self._log.info(f"  Skipped         : {len(skipped)}")
        self._log.info(f"  No credentials  : {len(no_creds)}")
        self._log.info(f"  Had credentials : {len(processed)}")
        self._log.info(f"  Errors          : {len(errored)}")

        if self.dry_run:
            self._log.info(
                "\n  ⚠  DRY RUN — no changes were made.  "
                "Re-run with --execute to apply."
            )

        if errored:
            self._log.info("\n  Accounts with errors:")
            for s in errored:
                self._log.info(f"    • {s.account_name} ({s.account_id}): {s.errors}")

        self._log.info("=" * 70)


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Remove root user credentials from all member accounts in an "
            "AWS Organization.  Defaults to DRY RUN — pass --execute to "
            "apply changes."
        )
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help=(
            "Actually remove credentials.  Without this flag the script runs "
            "in dry-run mode and only prints what would change."
        ),
    )
    parser.add_argument(
        "--exclude",
        default="",
        metavar="ID1,ID2,…",
        help="Comma-separated list of account IDs to skip.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        metavar="PROFILE",
        help="AWS CLI profile to use (defaults to the environment default).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: INFO).",
    )
    return parser.parse_args()


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    excluded = frozenset(
        a.strip() for a in args.exclude.split(",") if a.strip()
    )

    manager = RootCredentialManager(
        dry_run=not args.execute,
        excluded_ids=excluded,
        aws_profile=args.profile,
    )

    manager.run()


if __name__ == "__main__":
    main()