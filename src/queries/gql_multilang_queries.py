def get_product_query() -> str:
    return """
    query($productId: ID!, $channelId: ID!, $locale: String!) {
      store {
        products(filters: { ids: [$productId] }) {
          edges {
            node {
              id
              basicInformation {
                name
                description
              }
              overridesForLocale(localeContext: { channelId: $channelId, locale: $locale }) {
                basicInformation {
                  name
                  description
                }
              }
            }
          }
        }
        product(id: $productId) {
          images {
            edges {
              node {
                urlStandard
              }
            }
          }
        }
      }
    }
    """


def get_update_mutation() -> str:
    return """
    mutation SetProductBasicInformation(
      $input: SetProductBasicInformationInput!,
      $channelId: ID!,
      $locale: String!
    ) {
      product {
        setProductBasicInformation(input: $input) {
          product {
            id
            overridesForLocale(localeContext: {
              channelId: $channelId,
              locale: $locale
            }) {
              basicInformation {
                name
                description
              }
            }
          }
        }
      }
    }
    """


def get_delete_override_mutation(product_id: int, locale: str, field: str, channel_id: int) -> str:
    return f"""
    mutation {{
      product {{
        removeProductBasicInformationOverrides(
          input: {{
            productId: "bc/store/product/{product_id}",
            localeContext: {{
              channelId: "bc/store/channel/{channel_id}",
              locale: "{locale}"
            }},
            overridesToRemove: [{field}]
          }}
        ) {{
          product {{
            id
            overridesForLocale(localeContext: {{
              channelId: "bc/store/channel/{channel_id}",
              locale: "{locale}"
            }}) {{
              basicInformation {{
                name
                description
              }}
            }}
          }}
        }}
      }}
    }}
    """