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
No lambdas, no bare except blocks.  Every AWS call site is a plain direct
call wrapped in a single AWSCaller.invoke() method.  ClientError codes are
mapped to typed exceptions:

  FatalConfigError       — script-wide problem (feature not enabled, etc.)
  AccountSkippedError    — skip this account, continue to the next
  CredentialRemovalError — one deletion step failed; log it and keep going

SCP blocks (AccessDenied on a specific IAM action) are caught per-operation
and recorded in the account summary rather than crashing the run.
"""

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Optional

import boto3
from botocore.exceptions import ClientError

# ── Force regional STS endpoint — global endpoint does not support assume_root
os.environ["AWS_STS_REGIONAL_ENDPOINTS"] = "regional"
STS_REGION       = "us-east-1"
TASK_POLICY_ARN  = "arn:aws:iam::aws:policy/root-task/IAMDeleteRootUserCredentials"


# ─────────────────────────────────────────────────────────────────────────────
# Custom exceptions
# ─────────────────────────────────────────────────────────────────────────────

class FatalConfigError(RuntimeError):
    """Pre-flight failure — the script cannot continue at all.
    Examples: centralized root not enabled, no Organizations access."""


class AccountSkippedError(RuntimeError):
    """This account should be skipped; other accounts can still be processed.
    Examples: suspended account, assume_root denied by SCP."""


class CredentialRemovalError(RuntimeError):
    """A single credential-deletion step failed.
    The account summary records the failure; processing continues for other
    credential types on the same account."""


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AccountCredentialSummary:
    """Everything found and done (or previewed) for one member account."""
    account_id:          str
    account_name:        str
    has_login_profile:   bool = False
    access_key_ids:      list = field(default_factory=list)
    signing_cert_ids:    list = field(default_factory=list)
    mfa_serial_numbers:  list = field(default_factory=list)
    actions_taken:       list = field(default_factory=list)
    errors:              list = field(default_factory=list)
    skipped:             bool = False
    skip_reason:         str  = ""

    @property
    def has_any_credentials(self) -> bool:
        return (
            self.has_login_profile
            or bool(self.access_key_ids)
            or bool(self.signing_cert_ids)
            or bool(self.mfa_serial_numbers)
        )


# ─────────────────────────────────────────────────────────────────────────────
# AWSCaller — single, unified call dispatcher (no lambdas)
# ─────────────────────────────────────────────────────────────────────────────

class AWSCaller:
    """
    Wraps every boto3 API call so that ClientError codes are translated into
    typed exceptions with full diagnostic context.

    Usage
    ─────
    Each call site does:

        result = AWSCaller.invoke(
            client_method,          # the bound boto3 method object
            _context="...",         # diagnostic label  (AWSCaller kwarg)
            _account_id="...",      # account label     (AWSCaller kwarg)
            _skip_codes={...},      # codes → AccountSkippedError
            _fatal_codes={...},     # codes → FatalConfigError
            _benign_codes={...},    # codes → return None quietly
            kwarg1=val1,            # real boto3 parameters
        )

    AWSCaller kwargs are prefixed with _ so they never collide with real
    boto3 parameter names.

    Returns the boto3 response dict on success, or None for benign codes.
    Raises FatalConfigError / AccountSkippedError / CredentialRemovalError.
    """

    # Codes that mean "resource doesn't exist" — silently return None
    DEFAULT_BENIGN = frozenset({"NoSuchEntity", "DeleteConflict"})

    @staticmethod
    def invoke(
        method,
        *,
        _context:      str,
        _account_id:   str                 = "",
        _skip_codes:   frozenset           = frozenset(),
        _fatal_codes:  frozenset           = frozenset(),
        _benign_codes: Optional[frozenset] = None,
        **boto3_kwargs,
    ):
        """
        Parameters
        ──────────
        method         Bound boto3 client method (e.g. iam_client.get_login_profile).
                       Pass the method object directly — no lambdas, no strings.
        _context       Human-readable label used in error messages.
        _account_id    Account being processed (used in error messages).
        _skip_codes    ClientError codes that raise AccountSkippedError.
        _fatal_codes   ClientError codes that raise FatalConfigError.
        _benign_codes  ClientError codes that return None quietly.
                       Defaults to DEFAULT_BENIGN {"NoSuchEntity", "DeleteConflict"}.
        **boto3_kwargs Passed directly to the boto3 method call.
        """
        benign = _benign_codes if _benign_codes is not None else AWSCaller.DEFAULT_BENIGN

        try:
            return method(**boto3_kwargs)

        except ClientError as exc:
            code    = exc.response["Error"]["Code"]
            message = exc.response["Error"]["Message"]
            detail  = f"[account={_account_id}] {_context} → {code}: {message}"

            if code in benign:
                return None                      # nothing to do — not an error

            if code in _fatal_codes:
                raise FatalConfigError(detail) from exc

            if code in _skip_codes:
                raise AccountSkippedError(detail) from exc

            raise CredentialRemovalError(detail) from exc


# ─────────────────────────────────────────────────────────────────────────────
# SessionFactory
# ─────────────────────────────────────────────────────────────────────────────

class SessionFactory:
    """
    Vends a scoped boto3 IAM client for a target member account by calling
    sts:AssumeRoot with the IAMDeleteRootUserCredentials task policy.

    The returned IAM client carries 15-minute root-scoped temporary credentials
    — enough to audit and delete all credential types for one account.
    """

    def __init__(self, base_session: boto3.Session):
        # Must target a regional STS endpoint — global is not supported for AssumeRoot
        self._sts = base_session.client("sts", region_name=STS_REGION)

    def get_root_iam_client(self, account_id: str):
        """
        Returns a boto3 IAM client with temporary root credentials scoped to
        account_id.

        Raises AccountSkippedError if access is denied (SCP, suspended account).
        Raises FatalConfigError if centralized root management is not enabled.
        """
        response = AWSCaller.invoke(
            self._sts.assume_root,
            _context      = "sts:AssumeRoot",
            _account_id   = account_id,
            _skip_codes   = frozenset({
                "AccessDenied",
                "AccountSuspended",
                "AWSOrganizationsNotInUseException",
            }),
            _fatal_codes  = frozenset({
                "RootCredentialsManagementNotEnabled",
            }),
            _benign_codes = frozenset(),     # no benign codes for AssumeRoot
            TargetPrincipal = account_id,
            TaskPolicyArn   = {"arn": TASK_POLICY_ARN},
        )

        creds   = response["Credentials"]
        session = boto3.Session(
            aws_access_key_id     = creds["AccessKeyId"],
            aws_secret_access_key = creds["SecretAccessKey"],
            aws_session_token     = creds["SessionToken"],
        )
        return session.client("iam", region_name=STS_REGION)


# ─────────────────────────────────────────────────────────────────────────────
# RootCredentialAuditor
# ─────────────────────────────────────────────────────────────────────────────

class RootCredentialAuditor:
    """
    Reads the current root credential state of a member account.
    Makes no changes.

    Each read operation is wrapped individually so that an SCP blocking one
    specific action (e.g. iam:GetLoginProfile) does not prevent the others
    (e.g. iam:ListAccessKeys) from running.  Failures are recorded in the
    summary as audit warnings.
    """

    def __init__(self, iam_client, logger: logging.Logger):
        self._iam = iam_client
        self._log = logger

    def get_summary(self, account_id: str, account_name: str) -> AccountCredentialSummary:
        summary = AccountCredentialSummary(
            account_id   = account_id,
            account_name = account_name,
        )

        # ── Login profile (console password) ─────────────────────────────────
        # NoSuchEntity → no password is set, which is the desired end state
        # Any other ClientError (e.g. SCP AccessDenied) is caught and logged
        try:
            resp = AWSCaller.invoke(
                self._iam.get_login_profile,
                _context      = "iam:GetLoginProfile",
                _account_id   = account_id,
                _benign_codes = frozenset({"NoSuchEntity"}),
            )
            summary.has_login_profile = (resp is not None)

        except CredentialRemovalError as exc:
            self._log.warning(f"  Could not check login profile: {exc}")
            summary.errors.append(f"Audit skipped (GetLoginProfile): {exc}")

        # ── Access keys ───────────────────────────────────────────────────────
        try:
            resp = AWSCaller.invoke(
                self._iam.list_access_keys,
                _context    = "iam:ListAccessKeys",
                _account_id = account_id,
            )
            if resp:
                summary.access_key_ids = [
                    k["AccessKeyId"]
                    for k in resp.get("AccessKeyMetadata", [])
                ]

        except CredentialRemovalError as exc:
            self._log.warning(f"  Could not list access keys: {exc}")
            summary.errors.append(f"Audit skipped (ListAccessKeys): {exc}")

        # ── Signing certificates ──────────────────────────────────────────────
        try:
            resp = AWSCaller.invoke(
                self._iam.list_signing_certificates,
                _context    = "iam:ListSigningCertificates",
                _account_id = account_id,
            )
            if resp:
                summary.signing_cert_ids = [
                    c["CertificateId"]
                    for c in resp.get("Certificates", [])
                ]

        except CredentialRemovalError as exc:
            self._log.warning(f"  Could not list signing certificates: {exc}")
            summary.errors.append(f"Audit skipped (ListSigningCertificates): {exc}")

        # ── MFA devices ───────────────────────────────────────────────────────
        try:
            resp = AWSCaller.invoke(
                self._iam.list_mfa_devices,
                _context    = "iam:ListMFADevices",
                _account_id = account_id,
            )
            if resp:
                summary.mfa_serial_numbers = [
                    d["SerialNumber"]
                    for d in resp.get("MFADevices", [])
                ]

        except CredentialRemovalError as exc:
            self._log.warning(f"  Could not list MFA devices: {exc}")
            summary.errors.append(f"Audit skipped (ListMFADevices): {exc}")

        return summary


# ─────────────────────────────────────────────────────────────────────────────
# RootCredentialRemover
# ─────────────────────────────────────────────────────────────────────────────

class RootCredentialRemover:
    """
    Removes every root credential listed in an AccountCredentialSummary.

    Each deletion step is independent.  If one fails (e.g. an SCP blocks
    iam:DeleteLoginProfile but allows iam:DeleteAccessKey), the error is
    recorded in summary.errors and the remaining steps still execute.
    """

    def __init__(self, iam_client, logger: logging.Logger):
        self._iam = iam_client
        self._log = logger

    def remove_all(self, summary: AccountCredentialSummary) -> None:
        aid = summary.account_id

        if summary.has_login_profile:
            self._delete_login_profile(aid, summary)

        for key_id in summary.access_key_ids:
            self._delete_access_key(aid, key_id, summary)

        for cert_id in summary.signing_cert_ids:
            self._delete_signing_certificate(aid, cert_id, summary)

        for serial in summary.mfa_serial_numbers:
            self._deactivate_mfa_device(aid, serial, summary)

    # ── private per-credential helpers ────────────────────────────────────────

    def _delete_login_profile(self, account_id: str, summary: AccountCredentialSummary) -> None:
        try:
            AWSCaller.invoke(
                self._iam.delete_login_profile,
                _context      = "iam:DeleteLoginProfile",
                _account_id   = account_id,
                _benign_codes = frozenset({"NoSuchEntity"}),   # already gone
            )
            summary.actions_taken.append("Deleted login profile (console password)")

        except CredentialRemovalError as exc:
            err = f"Failed to delete login profile: {exc}"
            summary.errors.append(err)
            self._log.error(f"  ✗ {err}")

    def _delete_access_key(self, account_id: str, key_id: str, summary: AccountCredentialSummary) -> None:
        # Must deactivate before deleting (AWS requirement)
        try:
            AWSCaller.invoke(
                self._iam.update_access_key,
                _context    = f"iam:UpdateAccessKey({key_id}) → Inactive",
                _account_id = account_id,
                AccessKeyId = key_id,
                Status      = "Inactive",
            )
        except CredentialRemovalError as exc:
            err = f"Failed to deactivate access key {key_id} — skipping deletion: {exc}"
            summary.errors.append(err)
            self._log.error(f"  ✗ {err}")
            return   # do not attempt deletion if deactivation failed

        try:
            AWSCaller.invoke(
                self._iam.delete_access_key,
                _context    = f"iam:DeleteAccessKey({key_id})",
                _account_id = account_id,
                AccessKeyId = key_id,
            )
            summary.actions_taken.append(f"Deleted access key {key_id}")

        except CredentialRemovalError as exc:
            err = f"Failed to delete access key {key_id}: {exc}"
            summary.errors.append(err)
            self._log.error(f"  ✗ {err}")

    def _delete_signing_certificate(self, account_id: str, cert_id: str, summary: AccountCredentialSummary) -> None:
        try:
            AWSCaller.invoke(
                self._iam.delete_signing_certificate,
                _context      = f"iam:DeleteSigningCertificate({cert_id})",
                _account_id   = account_id,
                CertificateId = cert_id,
            )
            summary.actions_taken.append(f"Deleted signing certificate {cert_id}")

        except CredentialRemovalError as exc:
            err = f"Failed to delete signing certificate {cert_id}: {exc}"
            summary.errors.append(err)
            self._log.error(f"  ✗ {err}")

    def _deactivate_mfa_device(self, account_id: str, serial: str, summary: AccountCredentialSummary) -> None:
        try:
            AWSCaller.invoke(
                self._iam.deactivate_mfa_device,
                _context     = f"iam:DeactivateMFADevice({serial})",
                _account_id  = account_id,
                SerialNumber = serial,
            )
            summary.actions_taken.append(f"Deactivated MFA device {serial}")

        except CredentialRemovalError as exc:
            err = f"Failed to deactivate MFA device {serial}: {exc}"
            summary.errors.append(err)
            self._log.error(f"  ✗ {err}")


# ─────────────────────────────────────────────────────────────────────────────
# OrganizationAccountLister
# ─────────────────────────────────────────────────────────────────────────────

class OrganizationAccountLister:
    """Paginates through all ACTIVE member accounts in the Organization.

    Note: the management account is never returned by list_accounts, so it
    is implicitly safe and does not need to be explicitly excluded.
    """

    def __init__(self, base_session: boto3.Session):
        self._orgs = base_session.client("organizations", region_name=STS_REGION)

    def list_accounts(self, excluded_ids: frozenset) -> list[dict]:
        """
        Returns a list of {Id, Name} dicts for all non-excluded ACTIVE accounts.
        Raises FatalConfigError if Organizations is inaccessible.
        """
        # get_paginator is a local SDK call — it does not hit the AWS API
        paginator    = self._orgs.get_paginator("list_accounts")
        page_iterator = AWSCaller.invoke(
            paginator.paginate,
            _context     = "organizations:ListAccounts paginate()",
            _fatal_codes = frozenset({
                "AWSOrganizationsNotInUseException",
                "AccessDeniedException",
            }),
        )

        accounts = []
        for page in page_iterator:
            for acct in page.get("Accounts", []):
                if acct["Status"] != "ACTIVE":
                    continue
                if acct["Id"] in excluded_ids:
                    continue
                accounts.append({"Id": acct["Id"], "Name": acct["Name"]})

        return accounts


# ─────────────────────────────────────────────────────────────────────────────
# RootCredentialManager — top-level orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class RootCredentialManager:
    """
    Iterates every active member account, audits root credentials, then
    removes them (unless dry_run=True).
    """

    def __init__(
        self,
        *,
        dry_run:      bool          = True,
        excluded_ids: frozenset     = frozenset(),
        aws_profile:  Optional[str] = None,
    ):
        self.dry_run      = dry_run
        self.excluded_ids = excluded_ids
        self._session     = boto3.Session(profile_name=aws_profile)
        self._lister      = OrganizationAccountLister(self._session)
        self._factory     = SessionFactory(self._session)
        self._results:    list[AccountCredentialSummary] = []
        self._log         = logging.getLogger(self.__class__.__name__)

    # ── public entry point ────────────────────────────────────────────────────

    def run(self) -> list[AccountCredentialSummary]:
        mode = (
            "DRY RUN — no changes will be made"
            if self.dry_run
            else "EXECUTE — credentials will be removed"
        )
        self._log.info("=" * 70)
        self._log.info("  Root Credential Removal")
        self._log.info(f"  Mode: {mode}")
        self._log.info("=" * 70)

        accounts = self._lister.list_accounts(self.excluded_ids)
        self._log.info(f"Found {len(accounts)} active member account(s) to process.\n")

        for acct in accounts:
            summary = self._process_account(acct["Id"], acct["Name"])
            self._results.append(summary)

        self._print_report()
        return self._results

    # ── private helpers ───────────────────────────────────────────────────────

    def _process_account(self, account_id: str, account_name: str) -> AccountCredentialSummary:
        self._log.info(f"── {account_name} ({account_id})")

        # Step 1 — obtain a scoped root IAM client for this account
        try:
            iam_client = self._factory.get_root_iam_client(account_id)

        except AccountSkippedError as exc:
            self._log.warning(f"  SKIPPED: {exc}\n")
            return AccountCredentialSummary(
                account_id   = account_id,
                account_name = account_name,
                skipped      = True,
                skip_reason  = str(exc),
            )

        except FatalConfigError:
            raise   # re-raise — script-wide problem, stop immediately

        # Step 2 — audit current credential state
        auditor = RootCredentialAuditor(iam_client, self._log)
        summary = auditor.get_summary(account_id, account_name)

        if not summary.has_any_credentials and not summary.errors:
            self._log.info("  No root credentials found — nothing to do.\n")
            return summary

        # Step 3 — print what was found
        self._log.info(f"  Login profile  : {'YES' if summary.has_login_profile else 'no'}")
        self._log.info(f"  Access keys    : {summary.access_key_ids      or 'none'}")
        self._log.info(f"  Signing certs  : {summary.signing_cert_ids    or 'none'}")
        self._log.info(f"  MFA devices    : {summary.mfa_serial_numbers  or 'none'}")

        if summary.errors:
            for audit_err in summary.errors:
                self._log.warning(f"  Audit warning  : {audit_err}")

        if self.dry_run:
            self._log.info("  [DRY RUN] Would remove the credentials listed above.\n")
            return summary

        # Step 4 — execute removals
        remover = RootCredentialRemover(iam_client, self._log)
        remover.remove_all(summary)

        for action in summary.actions_taken:
            self._log.info(f"  ✓ {action}")

        self._log.info("")
        return summary

    def _print_report(self) -> None:
        self._log.info("=" * 70)
        self._log.info("  SUMMARY REPORT")
        self._log.info("=" * 70)

        skipped   = [s for s in self._results if s.skipped]
        no_creds  = [s for s in self._results if not s.skipped and not s.has_any_credentials and not s.errors]
        processed = [s for s in self._results if not s.skipped and (s.has_any_credentials or s.errors)]
        errored   = [s for s in processed if s.errors]

        self._log.info(f"  Total accounts  : {len(self._results)}")
        self._log.info(f"  Skipped         : {len(skipped)}")
        self._log.info(f"  No credentials  : {len(no_creds)}")
        self._log.info(f"  Had credentials : {len(processed)}")
        self._log.info(f"  With errors     : {len(errored)}")

        if self.dry_run:
            self._log.info(
                "\n  ⚠  DRY RUN — no changes were made.\n"
                "     Re-run with --execute to apply changes."
            )

        if skipped:
            self._log.info("\n  Skipped accounts:")
            for s in skipped:
                self._log.info(f"    • {s.account_name} ({s.account_id}): {s.skip_reason}")

        if errored:
            self._log.info("\n  Accounts with errors:")
            for s in errored:
                for err in s.errors:
                    self._log.info(f"    • {s.account_name} ({s.account_id}): {err}")

        self._log.info("=" * 70)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Remove root user credentials from all member accounts in an AWS "
            "Organization.  Defaults to dry-run; pass --execute to apply."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python remove_root_credentials.py
  python remove_root_credentials.py --execute
  python remove_root_credentials.py --execute --exclude 111122223333,444455556666
  python remove_root_credentials.py --execute --profile my-mgmt-profile
        """,
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Apply changes. Without this flag the script is a dry-run only.",
    )
    parser.add_argument(
        "--exclude",
        default="",
        metavar="ID1,ID2",
        help="Comma-separated account IDs to skip.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        metavar="PROFILE",
        help="AWS CLI profile to use (default: environment default).",
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
        level   = getattr(logging, level),
        format  = "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt = "%Y-%m-%dT%H:%M:%S",
        stream  = sys.stdout,
    )


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)

    excluded = frozenset(a.strip() for a in args.exclude.split(",") if a.strip())

    manager = RootCredentialManager(
        dry_run      = not args.execute,
        excluded_ids = excluded,
        aws_profile  = args.profile,
    )
    manager.run()


if __name__ == "__main__":
    main()