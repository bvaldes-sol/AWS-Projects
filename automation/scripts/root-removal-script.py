import boto3
from botocore.exceptions import ClientError
from typing import List, Dict, Any

class AwsOrganizationManager:
    """Handles AWS Organizations operations: listing accounts, identifying management account."""

    def __init__(self):
        self.org_client = boto3.client('organizations')

    def get_management_account_id(self) -> str:
        """Retrieve the ID of the management (payer) account."""
        response = self.org_client.describe_organization()
        return response['Organization']['MasterAccountId']

    def list_all_accounts(self) -> List[Dict[str, Any]]:
        """List all accounts in the organization with pagination."""
        accounts = []
        paginator = self.org_client.get_paginator('list_accounts')
        for page in paginator.paginate():
            accounts.extend(page['Accounts'])
        return accounts


class RootCredentialRemover:
    """Performs credential removal (or dry-run simulation) in a single member account using AssumeRoot."""

    TASK_POLICY_ARN = 'arn:aws:iam::aws:policy/root-task/IAMDeleteRootUserCredentials'
    STS_REGION = 'us-east-1'  # AssumeRoot typically requires regional endpoint

    def __init__(self, account_id: str, dry_run: bool = True):
        self.account_id = account_id
        self.dry_run = dry_run
        self.sts_client = boto3.client('sts', region_name=self.STS_REGION)

    def _assume_root_session(self) -> boto3.Session:
        """Assume root credentials scoped to delete root credentials."""
        try:
            response = self.sts_client.assume_root(
                TargetPrincipal=self.account_id,
                TaskPolicyArn={'arn': self.TASK_POLICY_ARN},  # <-- This is the required fix: singular TaskPolicyArn as dict
                DurationSeconds=900
            )
            creds = response['Credentials']
            return boto3.Session(
                aws_access_key_id=creds['AccessKeyId'],
                aws_secret_access_key=creds['SecretAccessKey'],
                aws_session_token=creds['SessionToken']
            )
        except ClientError as e:
            error_info = e.response.get('Error', {})
            code = error_info.get('Code', 'Unknown')
            msg = error_info.get('Message', str(e))
            raise RuntimeError(f"AssumeRoot failed for {self.account_id}: {code} - {msg}") from e

    def _log(self, message: str):
        prefix = "(DRY RUN) " if self.dry_run else ""
        print(f"{prefix}{message}")

    def remove_credentials(self) -> None:
        """Main method: Assume root → remove credentials (or simulate)."""
        mode = "(DRY RUN — preview only)" if self.dry_run else "(LIVE — applying changes)"
        print(f"\nProcessing account: {self.account_id} {mode}")

        try:
            session = self._assume_root_session()
            iam = session.client('iam')

            # 1. Root Password (Login Profile)
            self._handle_login_profile(iam)

            # 2. Access Keys
            self._handle_access_keys(iam)

            # 3. Signing Certificates
            self._handle_signing_certificates(iam)

            # 4. MFA Devices
            self._handle_mfa_devices(iam)

            print(f"Completed account: {self.account_id} ✓")

        except ClientError as e:
            error_info = e.response.get('Error', {})
            code = error_info.get('Code', 'Unknown')
            msg = error_info.get('Message', str(e))
            print(f"Failed for {self.account_id}: {code} - {msg}")
        except Exception as e:
            print(f"Unexpected error for {self.account_id}: {str(e)}")

    def _handle_login_profile(self, iam):
        if self.dry_run:
            self._log("Would delete root login profile (password)")
            return

        try:
            iam.delete_login_profile()  # Omit UserName → defaults to caller (root)
            self._log("Root password deleted")
        except ClientError as e:
            if e.response['Error']['Code'] == 'NoSuchEntity':
                self._log("No root password exists")
            else:
                raise

    def _handle_access_keys(self, iam):
        response = iam.list_access_keys()
        keys = response.get('AccessKeyMetadata', [])
        for key in keys:
            key_id = key['AccessKeyId']
            if self.dry_run:
                self._log(f"Would delete access key: {key_id}")
            else:
                iam.delete_access_key(AccessKeyId=key_id)
                self._log(f"Deleted access key: {key_id}")

    def _handle_signing_certificates(self, iam):
        response = iam.list_signing_certificates()
        certs = response.get('Certificates', [])
        for cert in certs:
            cert_id = cert['CertificateId']
            if self.dry_run:
                self._log(f"Would delete signing certificate: {cert_id}")
            else:
                iam.delete_signing_certificate(CertificateId=cert_id)
                self._log(f"Deleted signing certificate: {cert_id}")

    def _handle_mfa_devices(self, iam):
        response = iam.list_mfa_devices()
        devices = response.get('MFADevices', [])
        for device in devices:
            serial = device['SerialNumber']
            if self.dry_run:
                self._log(f"Would deactivate MFA: {serial}")
            else:
                iam.deactivate_mfa_device(SerialNumber=serial)
                self._log(f"Deactivated MFA: {serial}")

            # Delete virtual MFA if applicable
            if serial.startswith('arn:aws:iam::'):
                if self.dry_run:
                    self._log(f"Would delete virtual MFA device: {serial}")
                else:
                    iam.delete_virtual_mfa_device(SerialNumber=serial)
                    self._log(f"Deleted virtual MFA device: {serial}")


class RootCredentialCleaner:
    """Orchestrates removal across all member accounts."""

    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        self.org_manager = AwsOrganizationManager()

    def run(self):
        management_id = self.org_manager.get_management_account_id()
        accounts = self.org_manager.list_all_accounts()

        print(f"Found {len(accounts)} accounts in organization. Management account: {management_id}")

        for account in accounts:
            account_id = account['Id']
            if account_id == management_id:
                print(f"Skipping management account: {account_id}")
                continue

            if account['Status'] != 'ACTIVE':
                print(f"Skipping non-active account: {account_id} ({account['Status']})")
                continue

            remover = RootCredentialRemover(account_id, dry_run=self.dry_run)
            remover.remove_credentials()


if __name__ == "__main__":
    # Set dry_run=False when ready to apply changes
    cleaner = RootCredentialCleaner(dry_run=True)
    cleaner.run()