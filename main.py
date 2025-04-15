#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import csv
import logging
import os
import re
import sys

from openai import AzureOpenAI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Precompile the regex to match title lines (e.g., "1. Title")
TITLE_PATTERN = re.compile(r"^[0-9]{1,2}\.\s+(.+)")


def extract(client: AzureOpenAI, model: str, temperature: float, text: str) -> str:
    instructions = (
        "You are an excellent Japanese linguist. "
        "You need to extract all the meaningful 'entities' such as nouns, adjectives, and adverbs from the text. "
        "You must create a list of these entities separated with a comma."
    )

    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        messages=[
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": f"Extract the entities from the following text.\n{text}",
            },
        ],
    )
    return response.choices[0].message.content


def process_file(input_file: str, client: AzureOpenAI) -> (dict, dict):
    """
    Processes the input file to extract product titles and associated keywords.

    Returns:
        results: dict mapping product titles to lists of keyword IDs.
        keyword_to_id: dict mapping each unique keyword to its unique ID.
    """
    results = {}
    keyword_to_id = {}  # Mapping from keyword string to its unique ID
    current_title = None
    buffer_text = ""

    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            title_match = TITLE_PATTERN.match(line)
            if title_match:
                # When a new title is encountered, process any buffered text
                if buffer_text and current_title:
                    extracted = extract(
                        client=client,
                        model="gpt-4.1",
                        temperature=0.1,
                        text=buffer_text,
                    )
                    keywords = [k.strip() for k in extracted.split(",") if k.strip()]
                    keyword_ids = []
                    for keyword in keywords:
                        if keyword not in keyword_to_id:
                            keyword_to_id[keyword] = len(keyword_to_id) + 1
                        keyword_ids.append(keyword_to_id[keyword])
                    results[current_title] = keyword_ids
                    buffer_text = ""
                # Set the new title
                current_title = title_match.group(1)
            else:
                # Accumulate text for the current product
                buffer_text += line + "\n"

        # Process any remaining text in the buffer
        if buffer_text and current_title:
            extracted = extract(
                client=client, model="gpt-4.1", temperature=0.1, text=buffer_text
            )
            keywords = [k.strip() for k in extracted.split(",") if k.strip()]
            keyword_ids = []
            for keyword in keywords:
                if keyword not in keyword_to_id:
                    keyword_to_id[keyword] = len(keyword_to_id) + 1
                keyword_ids.append(keyword_to_id[keyword])
            results[current_title] = keyword_ids

    return results, keyword_to_id


def write_csv_files(results: dict, keyword_to_id: dict):
    # Write keywords.csv using the csv module
    with open("keywords.csv", "w", newline="", encoding="utf-8") as kf:
        writer = csv.writer(kf, quoting=csv.QUOTE_ALL)
        writer.writerow(["id", "Value"])
        # Ensure keywords are written in order of their assigned ID
        for keyword, keyword_id in sorted(keyword_to_id.items(), key=lambda kv: kv[1]):
            writer.writerow([keyword_id, keyword])

    # Write products.csv and has_keywords.csv concurrently
    with (
        open("products.csv", "w", newline="", encoding="utf-8") as pf,
        open("has_keywords.csv", "w", newline="", encoding="utf-8") as hkf,
    ):
        prod_writer = csv.writer(pf, quoting=csv.QUOTE_ALL)
        has_kw_writer = csv.writer(hkf, quoting=csv.QUOTE_ALL)

        prod_writer.writerow(["id", "Name"])
        has_kw_writer.writerow(
            ["id", "start_id", "start_vertex_type", "end_id", "end_vertex_type"]
        )

        product_id = 1
        has_keyword_id = 1
        for title, kw_ids in results.items():
            prod_writer.writerow([product_id, title.strip()])
            for kw_id in kw_ids:
                has_kw_writer.writerow(
                    [has_keyword_id, product_id, "Product", kw_id, "Keyword"]
                )
                has_keyword_id += 1
            product_id += 1


def main():
    parser = argparse.ArgumentParser(description="Extract entities from text")
    parser.add_argument("input_file", type=str, help="Input file containing text")
    args = parser.parse_args()

    if not os.path.isfile(args.input_file):
        logger.error("File '%s' does not exist.", args.input_file)
        sys.exit(1)

    endpoint = os.getenv("AOAI_GPT41_EP")
    api_key = os.getenv("AOAI_GPT41_KEY")
    if not endpoint or not api_key:
        logger.error(
            "Required environment variables AOAI_GPT41_EP and AOAI_GPT41_KEY must be set."
        )
        sys.exit(1)

    try:
        with AzureOpenAI(
            api_version="2024-12-01-preview", azure_endpoint=endpoint, api_key=api_key
        ) as client:
            results, keyword_to_id = process_file(args.input_file, client)
    except Exception as e:
        logger.error("Error processing file or initializing client: %s", e)
        sys.exit(1)

    write_csv_files(results, keyword_to_id)


if __name__ == "__main__":
    main()
