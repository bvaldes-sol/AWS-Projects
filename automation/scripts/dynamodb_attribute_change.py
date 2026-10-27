
import boto3
class DynamoDBAppender:
    """
    OOP Class for appending values to a DynamoDB attribute.
    - Configurable: filter by any attribute/value, target any attribute.
    - Handles string sets (SS) for now — adaptable for other types.
    - Appends multiple new values, deduping against existing.
    - Skips if all new values are already present (duplicates).
    - Initializes if empty/missing.
    - Pagination: automatic via paginator.
    - Dry run: previews changes without applying.
    """
    
    def __init__(self, table_name, filter_attribute, filter_value, target_attribute, new_values, dry_run=True, attr_type='set'):
        """
        Constructor: Sets up the object's data (attributes).
        - self.dynamodb: Boto3 client (shared across methods).
        - Other self.*: Your config params.
        - new_values: list of strings to append (or single str → converted to list)
        """
        self.dynamodb = boto3.client('dynamodb')
        self.table_name = table_name
        self.filter_attribute = filter_attribute  # e.g., 'ApplicationID'
        self.filter_value = filter_value          # e.g., '123'
        self.target_attribute = target_attribute  # e.g., 'country_codes'
        self.new_values = new_values if isinstance(new_values, list) else [new_values]  # Ensure list
        self.dry_run = dry_run
        self.attr_type = attr_type                # 'set' for SS; future: 'string' for colon-separated
        self.partition_key = 'accountid'          # Hardcoded for your table; could param this
        self.filter_attr_alias = '#filter_attr'   # Safe alias for reserved words
        
        # Quick validation
        if self.attr_type != 'set':
            raise ValueError("Currently only supports 'set' type — add more in future!")

    def scan_items(self):
        """Method: Fetches all matching items with pagination."""
        paginator = self.dynamodb.get_paginator('scan')

        page_iterator = paginator.paginate(
            TableName=self.table_name,
            FilterExpression=f'{self.filter_attr_alias} = :filter_val AND #isphi = :isphi_true',
            ExpressionAttributeNames={
                self.filter_attr_alias: self.filter_attribute,      # e.g. 'ApplicationID'
                '#isphi': 'isphi_temp'                              # safe alias for the boolean field
            },
            ExpressionAttributeValues={
                ':filter_val':   {'S': self.filter_value},          # your existing string value
                ':isphi_true':   {'BOOL': True}                     # boolean true
            }
        )  
              
        items = []
        for page in page_iterator:
            page_items = page.get('Items', [])
            items.extend(page_items)
            print(f"  Fetched {len(page_items)} items from this page...")
        
        print(f"\nTotal items found after full pagination: {len(items)}")
        return items

    def generate_previews(self, items):
        """Method: Builds preview changes + handles skips only for full duplicates."""
        preview_changes = []
        
        for item in items:
            account_id_value = item[self.partition_key]['S']
            key = {self.partition_key: {'S': account_id_value}}
            
            # Get current value (empty list if missing or empty set)
            current_values = item.get(self.target_attribute, {}).get('SS', [])
            
            # Convert to sets for easy dedup/check
            current_set = set(current_values)
            new_set = set(self.new_values)
            
            # Skip if ALL new values are already present (nothing would change)
            if new_set.issubset(current_set):
                print(f"Skipping accountid {account_id_value} — all new values already exist in {self.target_attribute}")
                continue
            
            # Special case: if currently empty → replace with exactly new_values
            if not current_values:
                updated_values = sorted(new_set)  # only the new ones
                preview_note = " (replacing empty value with new set)"
                to_add = list(new_set)
            else:
                # Normal case: add only what's missing
                to_add = list(new_set - current_set)
                updated_values = sorted(current_set | new_set)
                preview_note = ""
            
            preview_changes.append({
                'accountid': account_id_value,
                'current': current_values,
                'would_become': updated_values,
                'key': key,
                'to_add': to_add,
                'note': preview_note
            })
        
        return preview_changes

    def display_previews(self, preview_changes):
        """Method: Prints the preview."""
        print("\n" + "="*50)
        print("PREVIEW OF PROPOSED CHANGES (dry run)")
        print("="*50)
        
        if not preview_changes:
            print("No items would be updated (no matches or all new values are duplicates)")
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
            # For sets: Use ADD with only unique to-add (optional; ADD dedups anyway)
            if self.attr_type == 'set':
                self.dynamodb.update_item(
                    TableName=self.table_name,
                    Key=change['key'],
                    UpdateExpression=f'ADD {self.target_attribute} :new_set',
                    ExpressionAttributeValues={
                        ':new_set': {'SS': change['to_add']}
                    }
                )
            
            print(f"Updated accountid: {change['accountid']}")
        print("\nAll updates completed.")

    def run(self):
        """Main method: Orchestrates everything."""
        # Table check
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
        table_name='YourActualTableNameHere',
        filter_attribute='ApplicationID',  # Or whatever attr to filter on
        filter_value='123',                # The value to match
        target_attribute='country_codes',  # The set to append to
        new_values=['AA', 'BA', 'CA'],     # List of new values (or single str)
        dry_run=True,                      # Safe mode
        attr_type='set'                    # For string sets
    )
    
    appender.run()