from ultralytics import YOLO
import shutil
import os

def main():
    # We assume the dataset is downloaded to a directory named 'teacher' or 'teacher-1'
    dataset_dir = "teacher-1"
    yaml_path = os.path.join(dataset_dir, "data.yaml")
    
    if not os.path.exists(yaml_path):
        print(f"Dataset YAML not found at {yaml_path}.")
        print("Please ensure the dataset is properly downloaded and unzipped from Roboflow.")
        return
        
    print(f"Found dataset at {yaml_path}, starting training...")
    
    # Load a pretrained YOLOv8n model
    model = YOLO("yolov8n.pt")
    
    # Train the model on the custom dataset
    results = model.train(
        data=yaml_path,
        epochs=50,       # Adjust epochs as needed
        imgsz=640,       # Default for most Roboflow exports
        batch=16,
        name="teacher_model",
        exist_ok=True
    )
    
    # The best trained model is usually saved at runs/detect/teacher_model/weights/best.pt
    best_model_path = "runs/detect/teacher_model/weights/best.pt"
    if os.path.exists(best_model_path):
        # Move it to the models directory
        dest = os.path.join("models", "teacher.pt")
        os.makedirs("models", exist_ok=True)
        shutil.copy(best_model_path, dest)
        print(f"Successfully trained and saved the model to {dest}!")
        print("The system will now automatically use this model on next startup.")
    else:
        print("Training finished but best.pt was not found.")

if __name__ == "__main__":
    main()
