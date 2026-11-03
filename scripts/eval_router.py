"""Evaluation script for AI Router and Keyword Fallback Classifier."""
import os
import sys
import json
from collections import defaultdict

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.services.router import fallback_classify, classify_enquiry


def evaluate():
    seed_path = os.path.join(os.path.dirname(__file__), "..", "data", "enquiries_seed.json")
    if not os.path.exists(seed_path):
        print(f"Error: {seed_path} not found.")
        return

    with open(seed_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    api_key_present = bool(settings.anthropic_api_key.strip() and settings.anthropic_model.strip())
    print("=" * 70)
    print("AI ROUTER & CLASSIFIER EVALUATION REPORT")
    print(f"Total Cases: {len(cases)}")
    print(f"Live API Configured: {api_key_present} (Model: {settings.anthropic_model or 'None - Offline Fallback'})")
    print("=" * 70)

    categories = ["room", "wedding", "offsite", "complaint", "unsorted"]
    confusion = {exp: defaultdict(int) for exp in categories}

    tuning_correct = 0
    tuning_total = 0
    held_out_correct = 0
    held_out_total = 0

    print(f"\n{'ID':<10} | {'Expected':<10} | {'Predicted':<10} | {'Conf':<6} | {'Split':<10} | {'Match'}")
    print("-" * 70)

    for item in cases:
        cid = item["id"]
        raw = item["raw_message"]
        exp = item["expected_category"]
        is_tune = item.get("is_tune_set", False)

        if api_key_present:
            res, method = classify_enquiry(raw)
        else:
            res = fallback_classify(raw)
            method = "fallback"

        pred = "unsorted" if res.confidence < settings.ai_confidence_threshold else res.category
        confusion[exp][pred] += 1
        is_match = (pred == exp)

        if is_tune:
            tuning_total += 1
            if is_match:
                tuning_correct += 1
            split_label = "Tuning"
        else:
            held_out_total += 1
            if is_match:
                held_out_correct += 1
            split_label = "Held-out"

        print(f"{cid:<10} | {exp:<10} | {pred:<10} | {res.confidence:<6.2f} | {split_label:<10} | {'YES' if is_match else 'NO'}")

    print("-" * 70)
    total_correct = tuning_correct + held_out_correct
    total_cases = tuning_total + held_out_total

    print(f"\nTuning Set Accuracy:    {tuning_correct}/{tuning_total} = {tuning_correct/tuning_total*100:.1f}%")
    if held_out_total > 0:
        print(f"Held-out Set Accuracy:  {held_out_correct}/{held_out_total} = {held_out_correct/held_out_total*100:.1f}%")
    print(f"Overall Accuracy:       {total_correct}/{total_cases} = {total_correct/total_cases*100:.1f}%\n")

    # Confusion matrix
    print("=" * 70)
    print("CONFUSION MATRIX (Rows: Actual, Columns: Predicted)")
    print("=" * 70)
    header = f"{'Actual':<12} | " + " | ".join([f"{c:<9}" for c in categories])
    print(header)
    print("-" * len(header))
    for act in categories:
        row_str = f"{act:<12} | "
        for pred in categories:
            val = confusion[act][pred]
            row_str += f"{val:<9} | "
        print(row_str)
    print("=" * 70)


if __name__ == "__main__":
    evaluate()
