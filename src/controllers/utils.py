# In src/controllers/utils.py
import json

def deep_convert_to_dict(data):
    """
    Recursively convert any dict-like or list-like object (including
    protobuf composites) into standard Python dictionaries and lists.
    """
    ##print(f"--- DEBUG: deep_convert_to_dict ---")
    #print(f"   - Input data type: {type(data)}")

    # Base case: already a simple type
    if isinstance(data, (str, int, float, bool, type(None))):
        return data

    # ✅ Handle dict-like objects first
    if hasattr(data, 'items'):
        #print("   - Treating as a dict-like object.")
        return {str(key): deep_convert_to_dict(value) for key, value in data.items()}

    # ✅ Handle list-like objects second
    if hasattr(data, '__iter__') and not isinstance(data, (str, bytes, dict)):
        #print("   - Treating as a list-like object.")
        return [deep_convert_to_dict(item) for item in data]

    # Fallback
    #print(f"   - ⚠️ Fallback: Converting unknown type {type(data)} to string.")
    return str(data)
