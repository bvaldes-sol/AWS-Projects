import boto3
from botocore.exceptions import ClientError

class DynamoDBUpdater:
    """
    OOP Class for updating a DynamoDB attribute based on filters.
    - Configurable: filter by attribute/values (list), update target attribute/value.
    - Handles multiple filter values with IN.
    - Pagination: automatic via paginator.
    - Dry run: previews changes without applying.
    - Assumes partition key 'role_name' (no sort key).
    """
    
    def __init__(self, table_name, filter_attribute, filter_values, update_attribute, new_value, dry_run=True):
        """
        Constructor: Sets up the object's data (attributes).
        - filter_values: list of strings to match (e.g., ['val1', 'val2']).
        - Assumes filter_values are strings ('S'); adjust if other types.
        """
        self.dynamodb = boto3.client('dynamodb')
        self.table_name = table_name
        self.filter_attribute = filter_attribute          # e.g., 'attribute_name'
        self.filter_values = filter_values                # list e.g., ['val1', 'val2']
        self.update_attribute = update_attribute          # e.g., 'owner_email'
        self.new_value = new_value                        # e.g., 'new@email.com'
        self.dry_run = dry_run
        self.partition_key = 'role_name'                  # Your table's PK
        self.filter_attr_alias = '#filter_attr'           # Safe alias
        
        # Validation: ensure filter_values is list
        if not isinstance(self.filter_values, list) or not self.filter_values:
            raise ValueError("filter_values must be a non-empty list")

    def scan_items(self):
        """Method: Fetches all matching items with pagination."""
        paginator = self.dynamodb.get_paginator('scan')
        
        # Build dynamic FilterExpression for IN (e.g., #attr IN (:v1, :v2))
        value_placeholders = [f':v{i}' for i in range(len(self.filter_values))]
        filter_expr = f'{self.filter_attr_alias} IN ({", ".join(value_placeholders)})'
        
        expr_values = {f':v{i}': {'S': val} for i, val in enumerate(self.filter_values)}
        
        page_iterator = paginator.paginate(
            TableName=self.table_name,
            FilterExpression=filter_expr,
            ExpressionAttributeNames={
                self.filter_attr_alias: self.filter_attribute
            },
            ExpressionAttributeValues=expr_values
            # Optional: ProjectionExpression=f'{self.partition_key}, {self.filter_attribute}, {self.update_attribute}'
        )
        
        items = []
        for page in page_iterator:
            page_items = page.get('Items', [])
            items.extend(page_items)
            print(f"  Fetched {len(page_items)} items from this page...")
        
        print(f"\nTotal items found after full pagination: {len(items)}")
        return items

    def generate_previews(self, items):
        """Method: Builds preview changes (no skips — update all matches)."""
        preview_changes = []
        
        for item in items:
            pk_value = item[self.partition_key]['S']
            key = {self.partition_key: {'S': pk_value}}
            
            # Get current update_attr value (assume string; default empty str if missing)
            current_value = item.get(self.update_attribute, {}).get('S', '')
            
            preview_changes.append({
                'pk': pk_value,
                'current': current_value,
                'would_become': self.new_value,
                'key': key
            })
        
        return preview_changes

    def display_previews(self, preview_changes):
        """Method: Prints the preview."""
        print("\n" + "="*50)
        print("PREVIEW OF PROPOSED CHANGES (dry run)")
        print("="*50)
        
        if not preview_changes:
            print("No items matched the filter.")
        else:
            for change in preview_changes:
                print(f"{self.partition_key}: {change['pk']}")
                print(f"  Current {self.update_attribute}     : {change['current']}")
                print(f"  Would become {self.update_attribute}: {change['would_become']}")
                print("-" * 60)
            
            print(f"\nTotal items that would be updated: {len(preview_changes)}")

    def apply_updates(self, preview_changes):
        """Method: Applies real updates if not dry run."""
        if self.dry_run or not preview_changes:
            print("\nDRY_RUN is enabled (or no changes) — no updates applied.")
            return
        
        print("\nApplying real updates...")
        for change in preview_changes:
            self.dynamodb.update_item(
                TableName=self.table_name,
                Key=change['key'],
                UpdateExpression=f'SET {self.update_attribute} = :new_val',
                ExpressionAttributeValues={
                    ':new_val': {'S': self.new_value}  # Assume string; change type if needed
                }
            )
            print(f"Updated {self.partition_key}: {change['pk']}")
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
    updater = DynamoDBUpdater(
        table_name='YourActualTableNameHere',
        filter_attribute='attribute_name',         # Attr to filter on
        filter_values=['value1', 'value2'],        # List of values to match (IN)
        update_attribute='owner_email',            # Attr to update
        new_value='new.owner@email.com',           # New value to set
        dry_run=True                               # Safe mode
    )
    
    updater.run()