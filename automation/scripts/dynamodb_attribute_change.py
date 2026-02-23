import boto3
from botocore.exceptions import ClientError

class DynamoDBAppender:
    """
    OOP Class for appending values to a DynamoDB attribute.
    - Configurable: filter by any attribute/value, target any attribute.
    - Handles string sets (SS) for now — adaptable for other types.
    - Skips: empty/missing attr, or if new_value already exists.
    - Pagination: automatic via paginator.
    - Dry run: previews changes without applying.
    """
    
    def __init__(self, filter_attr_alias, table_name, filter_attribute, filter_value, target_attribute, new_value, dry_run=True, attr_type='set'):
        """
        Constructor: Sets up the object's data (attributes).
        - self.dynamodb: Boto3 client (shared across methods).
        - Other self.*: Your config params.
        """
        self.dynamodb          = boto3.client('dynamodb')
        self.filter_attr_alias = filter_attr_alias
        self.table_name        = table_name
        self.filter_attribute  = filter_attribute  # e.g., ''
        self.filter_value      = filter_value          # e.g., ''
        self.target_attribute  = target_attribute  # e.g., ''
        self.new_value         = new_value                # e.g., ''
        self.dry_run           = dry_run
        self.attr_type         = attr_type                # 'set' for SS; future: 'string' for colon-separated
        self.partition_key     = ''          # Hardcoded for your table; could param this
        
        # Quick validation (optional but good practice in OOP)
        if self.attr_type != 'set':
            raise ValueError("Currently only supports 'set' type — add more in future!")

    def scan_items(self):
        """Method: Fetches all matching items with pagination."""
        paginator = self.dynamodb.get_paginator('scan')
        
        page_iterator = paginator.paginate(
            TableName=self.table_name,
            FilterExpression=f'{self.filter_attr_alias} = :filter_val',
            ExpressionAttributeNames={
                self.filter_attr_alias: self.filter_attribute
            },
            ExpressionAttributeValues={
                ':filter_val': {'S': self.filter_value}
            }
            # Optional: ProjectionExpression=...
        )
        
        items = []
        for page in page_iterator:
            page_items = page.get('Items', [])
            items.extend(page_items)
            print(f"  Fetched {len(page_items)} items from this page...")
        
        print(f"\nTotal items found after full pagination: {len(items)}")
        return items

    def generate_previews(self, items):
        """Method: Builds preview changes + handles skips only for duplicates."""
        preview_changes = []
        
        for item in items:
            account_id_value = item[self.partition_key]['S']
            key = {self.partition_key: {'S': account_id_value}}
            
            # Get current value (empty list if missing or empty set)
            current_values = item.get(self.target_attribute, {}).get('SS', [])
            
            # Skip ONLY if the new value is already present
            if self.new_value in current_values:
                print(f"Skipping accountid {account_id_value} — '{self.new_value}' already exists in {self.target_attribute}")
                continue
            
            # For preview: show what it will become
            if not current_values:
                # Case: initializing the set
                updated_values = [self.new_value]
                preview_note = " (initializing set)"
            else:
                # Case: appending to existing set
                updated_values = current_values + [self.new_value]
                preview_note = ""
            
            preview_changes.append({
                'accountid': account_id_value,
                'current': current_values,
                'would_become': updated_values,
                'key': key,
                'note': preview_note   # optional - just for nicer display
            })
        
        return preview_changes


    def display_previews(self, preview_changes):
        """Method: Prints the preview."""
        print("\n" + "="*50)
        print("PREVIEW OF PROPOSED CHANGES (dry run)")
        print("="*50)
        
        if not preview_changes:
            print("No items would be updated (no matches or all duplicates)")
        else:
            for change in preview_changes:
                print(f"accountid: {change['accountid']}")
                print(f"  Current {self.target_attribute}     : {change['current']}")
                print(f"  Would become {self.target_attribute}: {change['would_become']}{change.get('note', '')}")
                print("-" * 60)
            
            print(f"\nTotal items that would be updated: {len(preview_changes)}")

    def apply_updates(self, preview_changes):
        """Method: Applies real updates if not dry run."""
        if self.dry_run or not preview_changes:
            print("\nDRY_RUN is enabled (or no changes) — no updates applied.")
            return
        
        print("\nApplying real updates...")
        for change in preview_changes:
            # For sets: Use ADD (handles uniqueness automatically)
            if self.attr_type == 'set':
                self.dynamodb.update_item(
                    TableName=self.table_name,
                    Key=change['key'],
                    UpdateExpression=f'ADD {self.target_attribute} :new_set',
                    ExpressionAttributeValues={
                        ':new_set': {'SS': [self.new_value]}
                    }
                )
            
            print(f"Updated accountid: {change['accountid']}")
        print("\nAll updates completed.")

    def run(self):
        """Main method: Orchestrates everything."""
        # Table check (will raise if table doesn't exist / permissions issue)
        desc = self.dynamodb.describe_table(TableName=self.table_name)
        print("Table status:", desc['Table']['TableStatus'])
        print("Primary key schema:", desc['Table']['KeySchema'])
    
        # Step 1: Scan
        items = self.scan_items()
    
        # Debug: First item if any
        if items:
            print("\nExample of first matching item:")
            print(items[0])
    
        # Step 2: Previews
        preview_changes = self.generate_previews(items)
    
        # Step 3: Display
        self.display_previews(preview_changes)
    
        # Step 4: Apply (if not dry run)
        self.apply_updates(preview_changes)

# How to use: Create an instance and run it
if __name__ == "__main__":
    # Example config (change these)
    appender = DynamoDBAppender(
        filter_attr_alias='#filter_attribute',
        table_name='YourActualTableNameHere',
        filter_attribute='',  # Or whatever attr to filter on
        filter_value='',                # The value to match
        target_attribute='',  # The set to append to
        new_value='',                    # The new code to add
        dry_run=True,                      # Safe mode
        attr_type='set'                    # For string sets
    )
    
    appender.run()

