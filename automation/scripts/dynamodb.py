import boto3
from botocore.exceptions import ClientError

# === CONFIG ===
TABLE_NAME     = 'YourActualTableNameHere'   # ← CHANGE THIS
TARGET_APP_ID  = '123'                       # ← CHANGE THIS (exact match needed!)
NEW_APPROVER   = 'jane.doe@example.com'      # ← what to append

dynamodb = boto3.client('dynamodb')  # assumes credentials/region are set

# For dry-run testing
DRY_RUN = True   # Change to False when ready to apply real updates

def main():
    try:
        # Optional: quick table check
        desc = dynamodb.describe_table(TableName=TABLE_NAME)
        print("Table status:", desc['Table']['TableStatus'])
        print("Primary key schema:", desc['Table']['KeySchema'])  # ← shows partition/sort keys

        # === Scan with filter (since ApplicationID is NOT the partition key) ===
        response = dynamodb.scan(
            TableName=TABLE_NAME,
            FilterExpression='ApplicationID = :app_id',
            ExpressionAttributeValues={
                ':app_id': {'S': TARGET_APP_ID}
            }
        )

        items = response.get('Items', [])

        # === DEBUG: See what we actually got ===
        print(f"\nScan returned {len(items)} items (Count: {response.get('Count', 0)})")
        print(f"Scanned {response.get('ScannedCount', 'N/A')} items total")
        if items:
            print("Example item keys:", list(items[0].keys()))
            print("First item full:", items[0])
        else:
            print("No matches found.")
            print(f"Filtered on: ApplicationID = '{TARGET_APP_ID}'")
            print("Possible issues:")
            print("  - Exact value mismatch (case-sensitive, no extra spaces)")
            print("  - 'ApplicationID' spelled wrong or different casing?")
            print("  - No items with that ApplicationID in this table?")
            print("  - Wrong table name / region?")
            return

        # === Collect previews ===
        preview_changes = []

        for item in items:
            # Primary key is accountid (simple PK)
            account_id_value = item['accountid']['S']

            key = {
                'accountid': {'S': account_id_value}
            }

            current_approvers = item.get('delegated_approvers', {}).get('S', '')
            separator = ', ' if current_approvers else ''
            updated_approvers = current_approvers + separator + NEW_APPROVER

            preview_changes.append({
                'accountid': account_id_value,
                'current': current_approvers,
                'would_become': updated_approvers,
                'key': key
            })

        # === Show preview ===
        print("\n=== PREVIEW OF PROPOSED CHANGES ===")
        if not preview_changes:
            print("No items would be updated.")
        else:
            for change in preview_changes:
                print(f"accountid: {change['accountid']}")
                print(f"  Current: '{change['current']}'")
                print(f"  Would become: '{change['would_become']}'")
                print("-" * 60)

            print(f"\nTotal items that would be updated: {len(preview_changes)}")

        # === Only apply if not dry-run ===
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
                print(f"Updated: {change['accountid']}")
        elif DRY_RUN:
            print("\nDRY RUN MODE — no changes were made to the database.")

    except ClientError as e:
        print("AWS Error:", e.response['Error']['Message'])
    except Exception as e:
        print("Unexpected error:", str(e))

if __name__ == "__main__":
    main()