from typing import Tuple, Dict, Any, Optional, List

def process_gql_locales(gql_response):
    locales_dict = {}
    try:
        edges = gql_response['data']['store']['locales']['edges']

        for edge in edges:
            node = edge.get('node', {})
            code = node.get('code')

            if code:
                locales_dict[code] = {
                    'status': node.get('status'),
                    'isDefault': node.get('isDefault')
                }
    except (KeyError, TypeError, AttributeError):
        pass
    return locales_dict

def process_gql_product_response(gql_response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        product_data = gql_response['data']['site']['product']

        if not product_data:
            return None
        processed_product = {
            'entityId': product_data.get('entityId'),
            'name': product_data.get('name'),
            'description': product_data.get('description'),
            'defaultImage': product_data.get('defaultImage')
        }

        images_list: List[Dict[str, str]] = []
        image_edges = product_data.get('images', {}).get('edges', [])
        if image_edges:
            for edge in image_edges:
                node = edge.get('node')
                if node:
                    images_list.append({
                        'url960wide': node.get('url960wide'),
                        'url1280wide': node.get('url1280wide')
                    })
        processed_product['images'] = images_list

        return processed_product

    except (KeyError, TypeError, AttributeError):

        return None