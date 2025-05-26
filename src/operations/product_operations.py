import os
import logging
from requests import HTTPError

from src.client.bc_client import BigCommerceClient

try:
    from src.config import BC_CHANNEL_ID
    CONFIG_IMPORTED = True
except ImportError:
    BC_CHANNEL_ID = os.getenv("BC_CHANNEL_ID")

logger = logging.getLogger(__name__)

class ProductOperations:
    def __init__(self, client: BigCommerceClient):
        self.client = client

    def get_bigcommerce_products(self, channel_id=BC_CHANNEL_ID):
        """Fetches all products for a given channel"""
        products = []
        page = 1
        while True:
            params = {
                "channel_id": channel_id,
                "limit": 250,
                "page": page,
                "include": "variants"
            }
            try:
                data =  self.client.rest(method="GET",endpoint= "/catalog/products", params=params)
                items = data.get("data", [])
                if not items:
                    break
                products.extend(items)
                page += 1
            except HTTPError as e:
                logger.error(f"Failed to fetch page {page} of products for channel {channel_id}: {e}")
                break
        logger.info(f"Retrieved {len(products)} products from BigCommerce channel={channel_id}")
        return products

    def create_bigcommerce_product(self, payload):
        """Creates a single product in BigCommerce."""
        try:
            return  self.client.rest(method="POST",endpoint= "/catalog/products", data=payload)
        except HTTPError as e:
            logger.error(f"Failed to create product via API. Payload: {payload}. Error: {e}")
            raise

    def bc_api_get_by_sku(self, sku: str) -> dict:
        """Fetches a product by its SKU."""
        params = {"sku": sku, "limit": 1}
        try:
            data =  self.client.rest(method="GET",endpoint= "/catalog/products", params=params)
            items = data.get("data", [])
            if items:
                return items[0]
            else:
                logger.debug(f"No product found for SKU: {sku}")
                return {}
        except HTTPError as e:
            logger.error(f"Error fetching product by SKU '{sku}': {e}")
            return {}

    def get_bc_product_images(self, product_id):
        """Fetches images for a specific product."""
        endpoint = f"/catalog/products/{product_id}/images"
        try:
            data =  self.client.rest("GET", endpoint)
            return data.get("data", [])
        except HTTPError as e:
            logger.error(f"Failed to fetch images for product {product_id}: {e}")
            return []


    def assign_channel(self, product_id, channel_id=BC_CHANNEL_ID):
        """Assigns a product to a specific channel."""
        payload = [{"product_id": product_id, "channel_id": channel_id}]
        try:
            self.client.rest(method="PUT",endpoint= "/catalog/products/channel-assignments", data=payload)
            logger.debug(f"Assigned product {product_id} to channel {channel_id}")
        except HTTPError as e:
            logger.error(f"Failed to assign product {product_id} to channel {channel_id}: {e}")


    def update_single_product(self, product_id, payload):
        """Updates a single product """
        endpoint = f"/catalog/products/{product_id}"
        try:
            return  self.client.rest("PUT", endpoint, data=payload)
        except HTTPError as e:
            logger.error(f"Failed to update single product ID={product_id}. Payload: {payload}. Error: {e}")
            raise

    def batch_update_products_api(self, products_chunk):
         """Sends a batch update request for multiple products."""
         if not products_chunk:
             logger.info("No products to update in batch API call.")
             return None
         payload = products_chunk
         ids_sample = [p.get('id', p.get('sku', '?')) for p in products_chunk[:3]]
         logger.debug(f"Sending batch update API call for {len(products_chunk)} products. Sample IDs/SKUs: {ids_sample}..")
         logger.info(f"Sending batch update API call for {len(products_chunk)} products.")
         response_data =  self.client.rest(method="PUT", endpoint="/catalog/products", data=payload)
         logger.debug(f"Batch update API call successful for {len(products_chunk)} products.")
         return response_data

    def get_bigcommerce_brands(self):
        """Fetches all brands"""
        all_brands = {}
        page = 1
        while True:
            params = {"page": page, "limit": 250}
            try:
                data = self.client.rest("GET", "/catalog/brands", params=params)
                brands = data.get("data", [])
                if not brands:
                    break
                for b in brands:
                    name_upper = b.get("name", "").strip().upper()
                    if name_upper:
                        all_brands[name_upper] = b.get("id")
                page += 1
            except HTTPError as e:
                logger.error(f"Failed to fetch page {page} of brands: {e}")
                break
        logger.info(f"Fetched {len(all_brands)} brands from BigCommerce.")
        return all_brands

    def create_brand_in_bigcommerce(self, brand_name):
        """Creates a new brand"""
        payload = {"name": brand_name, "is_visible": True}
        try:
            data = self.client.rest("catalog/brands", method="POST", data=payload, use_v3=True)
            new_id = data.get("data", {}).get("id")
            if new_id:
                logger.info(f"Created new brand '{brand_name}' with ID={new_id}")
                return new_id
            else:
                logger.error(f"Failed to create brand '{brand_name}'. Response: {data}")
                return None
        except HTTPError as e:
            logger.error(f"Error creating brand '{brand_name}': {e}")
            return None