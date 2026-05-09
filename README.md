# 🎓 辅导员学生管理系统 v2

轻量级辅导员工作管理工具，零依赖 Python 后端 + 纯前端 SPA。

## ✨ 功能

- **📊 工作台** — 仪表盘总览：学生数、今日日程、分类统计
- **👥 学生信息管理** — 增删改查、多维度搜索筛选、详情查看
- **📅 日程管理** — 日历/列表双视图、颜色分类、浏览器通知提醒
- **📂 分类筛选** — 资助/奖助/学业/党建/心理，快速定位

## 🛠 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python 3.10+（零依赖，标准库） |
| 前端 | 纯 HTML + CSS + JavaScript |
| 认证 | htpasswd + Session Token |
| 部署 | Nginx 反向代理 + systemd |

## 🚀 部署指南

### 1. 环境要求

- Python 3.10+
- Nginx
- apache2-utils（提供 `htpasswd` 命令）

```bash
sudo apt update && sudo apt install -y python3 nginx apache2-utils
```

### 2. 获取代码

```bash
git clone https://github.com/MoyuOlogy/counselor.git
cd counselor
```

### 3. 配置环境变量

```bash
cp .env.example .env
vim .env  # 填写实际配置
```

### 4. 创建认证用户

```bash
sudo htpasswd -c /etc/nginx/.htpasswd your_username
```

### 5. 配置 Nginx

创建 `/etc/nginx/sites-available/counselor`：

```nginx
server {
    listen 8082 ssl;
    server_name your-domain.com;

    ssl_certificate     /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        root /opt/counselor;
        index index.html;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/counselor /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 6. 启动服务

```bash
sudo cp counselor-web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable counselor-web
sudo systemctl start counselor-web
```

### 7. 访问

```
https://your-domain.com:8082
```

## 📁 项目结构

```
counselor/
├── server.py              # 后端服务（零依赖）
├── index.html             # 前端 SPA
├── data/                  # 数据存储目录
├── .env.example           # 环境变量模板
├── counselor-web.service  # systemd 服务
└── README.md
```

## 🔒 安全

- 认证：Nginx htpasswd + Session Token
- 输入 HTML 转义防 XSS
- 数据文件不纳入版本控制

## 📄 License

MIT
