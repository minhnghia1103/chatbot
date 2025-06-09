# Xử lý trong DB

### Truy cập vào DB
```bash
pgcli -h localhost -U minhnghia -d project2 -W
```

### Xem các bảng
```bash
\dt
```

### Xem 1 bảng
```bash
\d
```

### Xóa bảng
```bash
DROP TABLE IF EXISTS ten_bang;
```

### Khởi tạo db và cho data vào data
```bash
python db_prep.py
```

#PgAdmin
```
docker run -p 5050:80 --name my_pgadmin -e PGADMIN_DEFAULT_EMAIL=hello@gmail.com -e PGADMIN_DEFAULT_PASSWORD=minhnghia -d dpage/pgadmin4
```


