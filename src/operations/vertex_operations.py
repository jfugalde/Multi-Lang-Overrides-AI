def process_multilingual_output(raw_descriptions: dict, product_name: str) -> dict:
    structured_output = {}
    for lang, html_description in raw_descriptions.items():
        structured_output[lang] = {
            "product_name": product_name,
            "description": html_description
        }
    return structured_output