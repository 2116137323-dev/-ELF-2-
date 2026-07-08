#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <string.h>
#include <sys/time.h>

// 左轮编码器
#define GPIO_A_PATH "/sys/class/gpio/gpio96/value"
#define GPIO_B_PATH "/sys/class/gpio/gpio99/value"
// 右轮编码器
#define GPIO_A1_PATH "/sys/class/gpio/gpio105/value" // 38
#define GPIO_B1_PATH "/sys/class/gpio/gpio103/value" // 40

static long long now_us() {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (long long)tv.tv_sec * 1000000LL + (long long)tv.tv_usec;
}

static int read_gpio_value(int fd, const char *name) {
    char value = '0';
    ssize_t n = 0;

    if (lseek(fd, 0, SEEK_SET) < 0) {
        fprintf(stderr, "错误: 无法定位 GPIO %s。\n", name);
        return -1;
    }

    n = read(fd, &value, 1);
    if (n != 1) {
        fprintf(stderr, "错误: 无法读取 GPIO %s。\n", name);
        return -1;
    }

    if (value != '0' && value != '1') {
        fprintf(stderr, "错误: GPIO %s 返回非法值: %c\n", name, value);
        return -1;
    }

    return value - '0';
}

int main() {
    // 1. 打开 4 个 GPIO 文件
    int fdA = open(GPIO_A_PATH, O_RDONLY);
    int fdB = open(GPIO_B_PATH, O_RDONLY);
    int fdA1 = open(GPIO_A1_PATH, O_RDONLY);
    int fdB1 = open(GPIO_B1_PATH, O_RDONLY);
    
    if (fdA < 0 || fdB < 0 || fdA1 < 0 || fdB1 < 0) {
        fprintf(stderr, "错误: 无法打开 GPIO 文件。请确认 4 个引脚都已经 export 且 chmod 777。\n");
        return 1;
    }

    char bufA[2], bufB[2], bufA1[2], bufB1[2];
    int lastA, A, B;
    int lastA1, A1, B1;
    long count_L = 0; // 左轮计数
    long count_R = 0; // 右轮计数
    long long last_report_us = now_us();
    const long long report_interval_us = 200000;

    // 2. 初始状态读取
    lastA = read_gpio_value(fdA, "A");
    lastA1 = read_gpio_value(fdA1, "A1");
    if (lastA < 0 || lastA1 < 0) {
        close(fdA);
        close(fdB);
        close(fdA1);
        close(fdB1);
        return 1;
    }

    while (1) {
        A = read_gpio_value(fdA, "A");
        B = read_gpio_value(fdB, "B");
        A1 = read_gpio_value(fdA1, "A1");
        B1 = read_gpio_value(fdB1, "B1");
        if (A < 0 || B < 0 || A1 < 0 || B1 < 0) {
            break;
        }

        int changed = 0; // 标记这一帧是否有脉冲变化

        // 3. 左轮逻辑：检测 A 相上升沿
        if (A == 1 && lastA == 0) { 
            if (B == 0) count_L++;
            else count_L--;
            changed = 1;
        }
        
        // 4. 右轮逻辑：检测 A1 相上升沿
        if (A1 == 1 && lastA1 == 0) { 
            if (B1 == 0) count_R++;
            else count_R--;
            changed = 1;
        }

        // 5. 只有在数据发生变化时才输出，减轻 Python 端的解析压力
        if (changed) {
            // 输出格式：左轮,右轮 (与之前的 Python 代码完美匹配)
            printf("%ld,%ld\n", count_L, count_R);
            fflush(stdout); 
        }

        long long t_us = now_us();
        if (t_us - last_report_us >= report_interval_us) {
            fprintf(stderr, "L=%ld R=%ld A=%d B=%d A1=%d B1=%d\n", count_L, count_R, A, B, A1, B1);
            fflush(stderr);
            last_report_us = t_us;
        }

        lastA = A;
        lastA1 = A1;
        
        usleep(200); // 保持 5kHz 采样频率
    }

    // 理论上不会走到这里，但保持好习惯
    close(fdA);
    close(fdB);
    close(fdA1);
    close(fdB1);
    return 0;
}
