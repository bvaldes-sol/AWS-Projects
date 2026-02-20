import boto3
from botocore.exceptions import ClientError

# === CONFIG ===
TABLE_NAME     = 'YourActualTableNameHere'          # ← CHANGE THIS
TARGET_APP_ID  = '123'                              # ← CHANGE THIS (exact string match required)
NEW_APPROVER   = 'jane.doe@example.com'             # ← What to append each time

dynamodb = boto3.client('dynamodb')  # Assumes credentials/region are configured

# For safe testing — change to False only when you're ready to apply real changes
DRY_RUN = True

def main():
    try:
        # Quick table validation (optional but helpful)
        desc = dynamodb.describe_table(TableName=TABLE_NAME)
        print("Table status:", desc['Table']['TableStatus'])
        print("Primary key schema:", desc['Table']['KeySchema'])

        # === Use Paginator for scan to handle large result sets automatically ===
        paginator = dynamodb.get_paginator('scan')

        page_iterator = paginator.paginate(
            TableName=TABLE_NAME,
            FilterExpression='ApplicationID = :app_id',
            ExpressionAttributeValues={
                ':app_id': {'S': TARGET_APP_ID}
            },
            # Optional: reduce data transfer & RCUs
            # ProjectionExpression='accountid, ApplicationID, delegated_approvers',
            # PaginationConfig={'PageSize': 100}
        )

        items = []
        for page in page_iterator:
            page_items = page.get('Items', [])
            items.extend(page_items)
            print(f"  Fetched {len(page_items)} items from this page...")

        print(f"\nTotal items found after full pagination: {len(items)}")

        # === Debug: Show structure of results ===
        if items:
            print("\nExample of first matching item:")
            print(items[0])
            print("\nAll attribute names in first item:", list(items[0].keys()))
        else:
            print("\nNo items matched ApplicationID =", repr(TARGET_APP_ID))
            print("Possible reasons: value mismatch, wrong attr name, wrong table/region")
            return

        # === Build preview of what would change ===
        preview_changes = []

        for item in items:
            account_id_value = item['accountid']['S']
            key = {'accountid': {'S': account_id_value}}

            current_approvers = item.get('delegated_approvers', {}).get('S', '').strip()

            # Skip if empty
            if not current_approvers:
                print(f"Skipping accountid {account_id_value} — delegated_approvers is empty")
                continue

            # Split into list of approvers (handles colon separator)
            existing_approvers = current_approvers.split(':')

            # Skip if already present (exact match)
            if NEW_APPROVER in existing_approvers:
                print(f"Skipping accountid {account_id_value} — '{NEW_APPROVER}' already exists")
                continue

            # Safe to append
            updated_approvers = current_approvers + ':' + NEW_APPROVER

            preview_changes.append({
                'accountid': account_id_value,
                'current': current_approvers,
                'would_become': updated_approvers,
                'key': key
            })

        # === Display preview ===
        print("\n" + "="*50)
        print("PREVIEW OF PROPOSED CHANGES (dry run)")
        print("="*50)

        if not preview_changes:
            print("No items would be updated (all matching items had empty delegated_approvers or none matched)")
        else:
            for change in preview_changes:
                print(f"accountid: {change['accountid']}")
                print(f"  Current : {repr(change['current'])}")
                print(f"  Would become : {repr(change['would_become'])}")
                print("-" * 60)

            print(f"\nTotal items that would be updated: {len(preview_changes)}")

        # === Apply changes only if not dry-run ===
        if not DRY_RUN and preview_changes:
            print("\nApplying real updates...")
            for change in preview_changes:
                dynamodb.update_item(
                    TableName=TABLE_NAME,
                    Key=change['key'],
                    UpdateExpression='SET delegated_approvers = :new_val',
                    ExpressionAttributeValues={
                        ':new_val': {'S': change['would_become']}
                    }
                )
                print(f"Updated accountid: {change['accountid']}")
            print("\nAll updates completed.")
        else:
            print("\nDRY_RUN is enabled — no changes were made to DynamoDB.")

    except ClientError as e:
        print("AWS DynamoDB Error:", e.response['Error']['Message'])
    except Exception as e:
        print("Unexpected error:", str(e))

if __name__ == "__main__":
    main()