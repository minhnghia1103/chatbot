-- PostgreSQL schema for project2
DROP TABLE IF EXISTS orders_details CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS categories CASCADE;
DROP TABLE IF EXISTS customers CASCADE;
DROP TABLE IF EXISTS messages CASCADE;

CREATE TABLE IF NOT EXISTS customers (
    customer_id SERIAL PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    password VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    phone VARCHAR(15),
    address TEXT
);

CREATE TABLE IF NOT EXISTS categories (
    id_category SERIAL PRIMARY KEY,
    category_name VARCHAR(255) NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS products (
    product_id SERIAL PRIMARY KEY,
    url TEXT,
    image_url TEXT,
    product_name VARCHAR(500) NOT NULL,
    id_category INTEGER NOT NULL,
    description TEXT,
    price DECIMAL(12, 2) NOT NULL CHECK(price > 0),
    quantity INTEGER NOT NULL DEFAULT 100 CHECK(quantity >= 0),
    product_info TEXT,
    usage_instructions TEXT,
    FOREIGN KEY (id_category) REFERENCES categories (id_category)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(50) NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending', 'Shipped', 'Cancelled', 'Completed')),
    FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
);

CREATE TABLE IF NOT EXISTS orders_details (
    order_detail_id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK(quantity > 0),
    unit_price DECIMAL(12, 2) NOT NULL CHECK(unit_price > 0),
    FOREIGN KEY (order_id) REFERENCES orders (order_id),
    FOREIGN KEY (product_id) REFERENCES products (product_id)
);

CREATE TABLE IF NOT EXISTS messages (
    message_id SERIAL PRIMARY KEY,
    bot TEXT NOT NULL,
    user_message TEXT NOT NULL,
    bot_response TEXT NOT NULL,
    tool_calls JSONB,  -- Thêm cột để lưu tool calls
    tool_results JSONB,  -- Thêm cột để lưu kết quả tool
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default categories
INSERT INTO categories (category_name) VALUES 
    ('games-toys'),
    ('do-dung-nha-cua'),
    ('thoi-trang'),
    ('phu-kien')
ON CONFLICT (category_name) DO NOTHING;
