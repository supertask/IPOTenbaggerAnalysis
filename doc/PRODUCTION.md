gnicorn setting
        /etc/systemd/system/gunicorn.service
        cat config/gunicorn_settings.py
        journalctl -u gunicorn.service -f #realtime log

        sudo systemctl restart gunicorn
        sudo systemctl status gunicorn
        sudo systemctl start gunicorn
        sudo systemctl stop gunicorn


flask
        nohup python flask_app.py &
        ps ax|grep flask_app
        kill <pid>

nginx
        sudo systemctl reload nginx
        sudo systemctl start nginx
        sudo systemctl enable nginx
        sudo tail -n 20 /var/log/nginx/access.log
        sudo vim /etc/nginx/nginx.conf
        sudo vim /etc/nginx/sites-enabled/*

firewall
        sudo firewall-cmd --list-ports
        sudo firewall-cmd --permanent --add-port=80/tcp
        sudo firewall-cmd --reload