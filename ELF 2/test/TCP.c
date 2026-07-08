#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <errno.h>
#include <string.h>

int main() {
    // 1. 创建 Socket
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd < 0) {
        perror("Socket creation failed");
        return -1;
    }

    // 2. 端口复用设置
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    // 3. 绑定端口
    struct sockaddr_in addr = { .sin_family = AF_INET, .sin_port = htons(8080), .sin_addr.s_addr = INADDR_ANY };
    if (bind(server_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("Bind failed");
        return -1;
    }
    
    listen(server_fd, 5);
    printf("服务器已启动，等待连接 (端口: 8080)...\n");
    
    // 4. 打开驱动设备
    int drv_fd = open("/dev/my_serial", O_WRONLY);
    if (drv_fd < 0) {
        perror("打开驱动 /dev/my_serial 失败");
        return -1;
    }

    // 5. 外层循环
    while (1) {
        int client_fd = accept(server_fd, NULL, NULL);
        if (client_fd < 0) {
            perror("Accept failed");
            continue;
        }
        printf("客户端已连接！\n");
        
        // 6. 内层循环
        char buf[2]; 
        ssize_t bytes_received;

        while ((bytes_received = recv(client_fd, buf, 2, 0)) > 0) {
            printf("接收到 %zd 字节: ", bytes_received);
            for(int i = 0; i < bytes_received; i++) {
                printf("%c", buf[i]);
            }
            printf("\n");

            // 直接转发给驱动
            write(drv_fd, buf, bytes_received);
        }
        
        printf("客户端断开，关闭连接...\n");
        close(client_fd); // 修复：必须关闭当前 client_fd
    }


    close(drv_fd);
    close(server_fd);
    return 0;
}