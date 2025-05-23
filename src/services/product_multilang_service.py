from typing import Dict, Any, List, Union

from src.queries.gql_multilang_queries import (
    get_product_query,
    get_update_mutation,
    get_delete_override_mutation
)


class ProductLocalizationService:
    def __init__(self, client):
        self.client = client

    def get_localized_data(
        self,
        product_id: int,
        channel_id: int,
        locales: Union[str, List[str]]
    ) -> Dict[str, Dict[str, Any]]:
        if isinstance(locales, str):
            locales = [locales]

        results = {}

        for locale in locales:
            variables = {
                "productId": f"bc/store/product/{product_id}",
                "channelId": f"bc/store/channel/{channel_id}",
                "locale": locale,
            }

            response = self.client.graphql(
                get_product_query(),
                variables=variables,
                admin=True,
                locale=locale,
            )

            if not response:
                results[locale] = {"name": None, "description": None, "images": []}
                continue

            store_data = response.get("data", {}).get("store", {})
            product_node = (
                store_data.get("products", {}).get("edges", [{}])[0].get("node", {})
            )

            images = [
                img.get("node", {}).get("urlStandard")
                for img in store_data.get("product", {}).get("images", {}).get("edges", [])
            ]

            overrides = product_node.get("overridesForLocale") or {}
            localized = overrides.get("basicInformation") or {}
            fallback = product_node.get("basicInformation", {})

            results[locale] = {
                "name": localized.get("name") or fallback.get("name"),
                "description": localized.get("description") or fallback.get("description"),
                "images": images,
            }

        return results

    def update_localized_product(
            self,
            product_id: int,
            name: str,
            description: str,
            locale: str,
            channel_id: int = 1
    ) -> Dict[str, Any]:
        mutation = get_update_mutation()
        variables = {
            "input": {
                "productId": f"bc/store/product/{product_id}",
                "localeContext": {
                    "channelId": f"bc/store/channel/{channel_id}",
                    "locale": locale,
                },
                "data": {
                    "name": name,
                    "description": description,
                }
            },
            "channelId": f"bc/store/channel/{channel_id}",
            "locale": locale
        }

        return self.client.graphql(mutation, variables=variables, admin=True, locale=locale)

    def update_all_locales(
        self,
        product_id: int,
        localized_data: Dict[str, Dict[str, str]],
        channel_id: int = 1
    ) -> Dict[str, Any]:
        """
        Accepts: { "de": { "name": "x", "description": "y" }, "es": {...} }
        """
        results = {}
        for locale, data in localized_data.items():
            result = self.update_localized_product(
                product_id=product_id,
                name=data.get("name", ""),
                description=data.get("description", ""),
                locale=locale,
                channel_id=channel_id
            )
            print(f"Update {locale}: {result}")
            results[locale] = result
        return results

    def delete_localized_override(
        self,
        product_id: int,
        locale: str,
        fields_to_remove: List[str],
        channel_id: int = 1
    ) -> Dict[str, Any]:
        """
        Deletes specific override fields in one locale.
        Valid fields: PRODUCT_NAME_FIELD, PRODUCT_DESCRIPTION_FIELD
        """
        field_enum = ", ".join(fields_to_remove)
        mutation = get_delete_override_mutation(product_id, locale, field_enum, channel_id)
        return self.client.graphql(mutation, admin=True, locale=locale)

    def delete_all_locales(
        self,
        product_id: int,
        locales: List[str],
        fields_to_remove: List[str],
        channel_id: int = 1
    ) -> Dict[str, Any]:
        results = {}
        for locale in locales:
            result = self.delete_localized_override(
                product_id=product_id,
                locale=locale,
                fields_to_remove=fields_to_remove,
                channel_id=channel_id
            )
            results[locale] = result
        return results