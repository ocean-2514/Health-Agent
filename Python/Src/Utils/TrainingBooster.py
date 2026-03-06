import os
import sys
import torch
from pathlib import Path
from typing import Dict, List, Optional
from collections import Counter

# Add bysj and project root to path
project_root = Path(__file__).resolve().parents[4]
bysj_path = project_root / "bysj"
if str(bysj_path) not in sys.path:
    sys.path.append(str(bysj_path))

try:
    from models.bert_model import TransformerLogBERT
    from models.cnn_model import train_oil_cnn_model
    from models.yolo_model import train_transformer_defect_model
except ImportError as e:
    print(f"[TrainingBooster] Warning: Failed to import models from bysj: {e}")

class TrainingBooster:
    """
    Expert utility to trigger and optimize training for defect models.
    Implements advanced techniques like automated class weighting and warmup.
    """
    
    @staticmethod
    def optimize_bert_training(
        log_dir: str,
        epochs: int = 20,
        lr: float = 2e-5,
        batch_size: int = 4,
        save_path: str = "./finetuned_bert_boosted"
    ):
        """
        BERT training with optimized defaults for electricity transformer logs.
        """
        print(f"🚀 Starting Boosted BERT Training...")
        print(f"Config: Epochs={epochs}, LR={lr}, Batch={batch_size}")
        
        # Initialize model
        # Note: Local path needs to be valid. 
        base_bert = project_root / "resources" / "bert-base-chinese"
        if not base_bert.exists():
            base_bert = "bert-base-chinese"
            
        model = TransformerLogBERT(model_path=str(base_bert))
        
        # Improvement: Automated data check before training
        try:
            logs, labels = model.load_logs_from_dir(log_dir)
            counts = Counter(labels)
            print(f"Data Distribution: {dict(counts)}")
            
            # The original fine_tune already implements Murphy's class weighting
            # We just trigger it with better hparams
            final_path = model.fine_tune(
                log_root_dir=log_dir,
                epochs=epochs,
                lr=lr,
                batch_size=batch_size,
                save_path=save_path,
                warmup_ratio=0.15, # Increased warmup for stability
                weight_decay=0.01   # Standard AdamW decay
            )
            print(f"✅ BERT training complete. Model saved at: {final_path}")
            return final_path
        except Exception as e:
            print(f"❌ BERT Training Failed: {e}")
            return None

    @staticmethod
    def optimize_cnn_training(
        train_data: str,
        train_labels: str,
        save_path: str = "./oil_cnn_boosted.pth"
    ):
        """
        CNN training with early stopping and lr scheduling.
        """
        print(f"🚀 Starting Boosted CNN Training...")
        try:
            # We use the existing training function but ensure paths and params are optimal
            final_path = train_oil_cnn_model(
                train_data_path=train_data,
                train_labels_path=train_labels,
                num_epochs=150,
                lr=0.001,
                batch_size=32,
                model_save_path=save_path
            )
            print(f"✅ CNN training complete. Model saved at: {final_path}")
            return final_path
        except Exception as e:
            print(f"❌ CNN Training Failed: {e}")
            return None

    @staticmethod
    def optimize_yolo_training(
        dataset_root: str,
        epochs: int = 100,
        imgsz: int = 640
    ):
        """
        YOLO training with auto-augmentation and optimized config.
        """
        print(f"🚀 Starting Boosted YOLO Training...")
        try:
            final_path = train_transformer_defect_model(
                dataset_root=dataset_root,
                epochs=epochs,
                batch_size=16, # Increased if hardware allows
                imgsz=imgsz
            )
            print(f"✅ YOLO training complete. Best weights at: {final_path}")
            return final_path
        except Exception as e:
            print(f"❌ YOLO Training Failed: {e}")
            return None

if __name__ == "__main__":
    print("TrainingBooster Utility Ready.")
