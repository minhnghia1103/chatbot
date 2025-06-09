import pandas as pd

df = pd.read_csv("E:/llm/llm_engineering/project2/sales-ai-agent-langgraph/setupDatabase/data/product_details.csv")

# Loại bỏ dấu chấm hàng nghìn và chuyển sang float
df["Price"] = df["Price"].str.replace(".", "", regex=False).astype(float)

df.to_csv("products_clean.csv", index=False)
# Giờ df["Price"] sẽ là 255000.0 thay vì 255.000 (chuỗi)