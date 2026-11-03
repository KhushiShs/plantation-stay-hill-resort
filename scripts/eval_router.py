"""Evaluation script for AI Router and Keyword Fallback Classifier.

Reads both data/enquiries_seed.json (Tuning Set) and data/enquiries_holdout.json (Hold-out Set).
Prints separate accuracy metrics, detailed per-case comparison, and confusion matrices.
If ANTHROPIC_API_KEY is configured, shows real-AI vs fallback side by side.
"""
import os
import sys
import json
from collections import defaultdict

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.config import settings
from app.services.router import fallback_classify, classify_enquiry


def load_dataset(filename: str):
    path = os.path.join(os.path.dirname(__file__), "..", "data", filename)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate():
    tuning_cases = load_dataset("enquiries_seed.json")
    holdout_cases = load_dataset("enquiries_holdout.json")

    api_key_present = bool(settings.anthropic_api_key.strip() and settings.anthropic_model.strip())

    print("=" * 80)
    print("AI ROUTER & CLASSIFIER EVALUATION REPORT")
    print(f"Tuning Set Cases:  {len(tuning_cases)} (data/enquiries_seed.json)")
    print(f"Hold-out Cases:    {len(holdout_cases)} (data/enquiries_holdout.json)")
    print(f"Live Anthropic API Configured: {api_key_present} (Model: {settings.anthropic_model or 'None - Offline Fallback'})")
    print("=" * 80)

    categories = ["room", "wedding", "offsite", "complaint", "unsorted"]

    def run_split(cases, split_name):
        print(f"\n--- EVALUATING {split_name.upper()} ({len(cases)} cases) ---")
        confusion_fb = {exp: defaultdict(int) for exp in categories}
        confusion_ai = {exp: defaultdict(int) for exp in categories}
        fb_correct = 0
        ai_correct = 0
        misses_fb = []
        misses_ai = []

        if api_key_present:
            header = f"{'ID':<10} | {'Expected':<10} | {'Fallback':<10} | {'FbConf':<6} | {'FbMatch':<7} | {'RealAI':<10} | {'AIConf':<6} | {'AIMatch'}"
            print(header)
            print("-" * len(header))
        else:
            header = f"{'ID':<10} | {'Expected':<10} | {'Fallback':<10} | {'FbConf':<6} | {'FbMatch'}"
            print(header)
            print("-" * len(header))

        for item in cases:
            cid = item["id"]
            raw = item["raw_message"]
            exp = item["expected_category"]

            # Fallback run (always)
            fb_res = fallback_classify(raw)
            fb_pred = "unsorted" if fb_res.confidence < settings.ai_confidence_threshold else fb_res.category
            confusion_fb[exp][fb_pred] += 1
            fb_match = (fb_pred == exp)
            if fb_match:
                fb_correct += 1
            else:
                misses_fb.append((cid, exp, fb_pred, fb_res.confidence, raw))

            if api_key_present:
                ai_res, _ = classify_enquiry(raw)
                ai_pred = "unsorted" if ai_res.confidence < settings.ai_confidence_threshold else ai_res.category
                confusion_ai[exp][ai_pred] += 1
                ai_match = (ai_pred == exp)
                if ai_match:
                    ai_correct += 1
                else:
                    misses_ai.append((cid, exp, ai_pred, ai_res.confidence, raw))

                print(f"{cid:<10} | {exp:<10} | {fb_pred:<10} | {fb_res.confidence:<6.2f} | {'YES' if fb_match else 'NO':<7} | {ai_pred:<10} | {ai_res.confidence:<6.2f} | {'YES' if ai_match else 'NO'}")
            else:
                print(f"{cid:<10} | {exp:<10} | {fb_pred:<10} | {fb_res.confidence:<6.2f} | {'YES' if fb_match else 'NO'}")

        fb_acc = (fb_correct / len(cases) * 100) if cases else 0
        print("-" * len(header))
        print(f"Fallback Classifier Accuracy on {split_name}: {fb_correct}/{len(cases)} = {fb_acc:.1f}%")

        if api_key_present:
            ai_acc = (ai_correct / len(cases) * 100) if cases else 0
            print(f"Live Anthropic AI Accuracy on {split_name}:   {ai_correct}/{len(cases)} = {ai_acc:.1f}%")

        if misses_fb:
            print(f"\n[Fallback Misses on {split_name}]:")
            for cid, exp, pred, conf, raw in misses_fb:
                print(f"  * {cid}: Expected '{exp}', got '{pred}' (conf={conf:.2f}). Message: \"{raw}\"")
        else:
            print(f"\n[Fallback Misses on {split_name}]: None (100% accurate!)")

        # Confusion table for fallback
        print(f"\n[Fallback Confusion Matrix - {split_name}] (Rows: Actual, Cols: Predicted)")
        conf_hdr = f"{'Actual':<12} | " + " | ".join([f"{c:<9}" for c in categories])
        print(conf_hdr)
        print("-" * len(conf_hdr))
        for act in categories:
            row_str = f"{act:<12} | "
            for pred in categories:
                row_str += f"{confusion_fb[act][pred]:<9} | "
            print(row_str)

        if api_key_present:
            print(f"\n[Real AI Confusion Matrix - {split_name}] (Rows: Actual, Cols: Predicted)")
            print(conf_hdr)
            print("-" * len(conf_hdr))
            for act in categories:
                row_str = f"{act:<12} | "
                for pred in categories:
                    row_str += f"{confusion_ai[act][pred]:<9} | "
                print(row_str)

        return fb_correct, len(cases)

    # 1. Tuning Set
    run_split(tuning_cases, "Tuning Set (data/enquiries_seed.json)")

    # 2. Hold-out Set
    run_split(holdout_cases, "Hold-out Evaluation Set (data/enquiries_holdout.json)")


if __name__ == "__main__":
    evaluate()
