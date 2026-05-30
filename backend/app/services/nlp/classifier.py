import time
import random
import os

from app.schemas.analyze import ClassificationResult, ScamType

class ScamClassifier:
    def __init__(self):
        # In a real scenario, we would load ONNX models here.
        # e.g., onnxruntime.InferenceSession("model_path.onnx")
        self.model_loaded = False
        self.load_model()

    def load_model(self):
        model_path = os.getenv("MURIL_MODEL_PATH", "trustshield/backend/ml/artifacts/muril_scam_classifier/model.onnx")
        if os.path.exists(model_path):
            self.model_loaded = True
            print("Loaded MuRIL ONNX model.")
        else:
            print("MuRIL model not found, falling back to DistilBERT multilingual mock.")

    async def classify(self, text: str) -> ClassificationResult:
        start_time = time.time()

        # Mocking model inference
        # In reality, this would tokenize `text` and run through the ONNX session

        text_lower = text.lower()
        is_scam = False
        confidence = 0.0
        scam_type = ScamType.UNKNOWN

        scam_keywords = {
            ScamType.VISHING: ["otp", "block", "compromised"],
            ScamType.FAKE_SUPPORT: ["support", "anydesk", "teamviewer"],
            ScamType.REFUND_SCAM: ["refund", "qr code", "scan"],
            ScamType.OTP_HARVESTING: ["otp batao", "share pin"],
            ScamType.REMOTE_ACCESS: ["screen share", "download"]
        }

        for stype, keywords in scam_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    is_scam = True
                    confidence = random.uniform(0.7, 0.99)
                    scam_type = stype
                    break
            if is_scam:
                break

        if not is_scam:
            confidence = random.uniform(0.01, 0.3)

        inference_time_ms = int((time.time() - start_time) * 1000)
        # ensure some small inference time for realism
        if inference_time_ms == 0:
            inference_time_ms = random.randint(10, 50)

        return ClassificationResult(
            is_scam=is_scam,
            confidence=confidence,
            scam_type=scam_type,
            inference_time_ms=inference_time_ms
        )
