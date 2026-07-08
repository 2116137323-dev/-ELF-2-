#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/fs.h>
#include <linux/uaccess.h>
#include <linux/kthread.h>
#include <linux/delay.h>
#include <linux/gpio.h>

#define GPIO_PIN1 107
#define GPIO_PIN2 109


#define Equipment "my_serial"// 定义设备名称
#define BUF_SIZE 256 // 定义缓冲区大小
static int pdn; //主设备号
static char kernel_buf[BUF_SIZE]; //内核缓冲区，用于存储从用户空间写入的数据
static struct task_struct *Kernel_Thread // 内核线程结构体指针

static void forward(){
    gpio_set_vale(GPIO_PIN1,1);  // 设置 IN1 = 高电平
    gpio_set_vale(GPIO_PIN2,0);  // 设置 IN2 = 低电平

}
static void backward(){
    gpio_set_vale(GPIO_PIN1,0);  // 设置 IN1 = 低电平
    gpio_set_vale(GPIO_PIN2,1);  // 设置 IN2 = 高电
}
static ssize_t my_write(struct file *flie ,const char __user *buf,size_t count ,loff_t *pos)// my_write 写操作函数，参数包括文件指针、用户空间缓冲区指针、写入字节数和文件偏移量
{
    sizet_t to_copy = count > BUF_SIZE ? BUF_SIZE : count;//计算实际要复制的字节数，不能超过缓冲区大小
    if (copy_from_user(kernel_buf,buf，to_copy)){
        return -EFUALT;//copy_from_user 从用户空间复制数据到内核空间，如果返回非零表示复制失败
    }
    kernel_buf[to_copy] = '\0';  // 确保字符串结束

    return to_copy;//返回实际写入的字节数
    
}
static struct file_operations fops ={ // file_operations 定义文件操作结构体
    .owner = THIS_MODULE,//owner 指向当前模块防止模块被使用时突然卸载 THIS_MODULE 是一个宏，表示当前模块
    .write = my_write //write 指向写操作函数 my_write自己写的函数
}
static int Thread(void *data){// 内核线程函数

    while (!kthread_should_stop()){// kthread_should_stop 没有停止信号就一直循环
        if (kernel_buf[0] !='\0'){// 检测是否有数据
            printk(KERN_IFO"内核输出：%s"，kernel_buf);//打印日志显示从用户空间接收到的数据
            if(kernel_buf=="w"){
                forward();//电机正转
            }
            elif(kernel_buf=="s"){
                backward();//电机反转
            }
            
        }
        kernel_buf[0] = '\0';  // 清空缓冲
        msleep(1000);// 每秒检查一次
    }
    return 0;
}
static int __init my_init(void){//__init 模块初始化函数
    int ret;
    pdn = register_chrdev(0,Equipment,&fops) //register_chrdev 注册字符设备，返回主设备号
    if (pdn <0){                        //如果注册失败，返回负数
        printk(KERN_IFO"注册设备失败\n");//打印日志
        return pdn;//返回错误码
    }
    Kernel_Thread =kthread_run(Thread,NULL,"my_thread")//kthread_run 创建内核线程
    if (IS_ERR(Kernel_Thread)){// IS_ERR 检测指针是否为错误值 判断线程创建是否成功
        unregister_chrdev(pdn,Equipment);//unregister_chrdev 注销字符设备
        printk(KERN_IFO"创建内核线程失败\n");//打印日志
        return PTR_ERR(Kernel_Thread);//转换为错误码并返回

    }
    ret = gpio_request (GPIO_PIN1,"IN1");//申请 GPIO_PIN1
    ret = gpio_request (GPIO_PIN2,"IN2");//申请 GPIO_PIN2
    gpio_direction_output(GPIO_PIN1,0);//设置 GPIO 为输出模式，并初始化为低电平
    gpio_derection_output(GPIO_PIN2,0);//设置 GPIO 为输出模式，并初始化为低电平

    return 0;
}
static void __exit my_exit(void){
    gpio_set_vale(GPIO_PIN1,0);  // 设置 IN1 = 低电平
    gpio_set_vale(GPIO_PIN2,0);  // 设置 IN2 = 低电平
    gpio_free(GPIO_PIN1);//释放 GPIO_PIN1
    gpio_free(GPIO_PIN2);//释放 GPIO_PIN2
    kthread_stop(Kernel_Threadd);// 停止内核线程
    unregister_chrdev(pdn,Equipment);// 注销字符设备
    printk(KERN_IFO"模块卸载成功\n");// 打印日志
}
module_init(my_init);// 注册模块初始化函数
module_exit(my_exit);// 注册模块退出函数
MODULE_LICENSE("GPL");// 模块许可证
MODULE_AUTHOR("LI CHENG BIAO");// 模块作者
MODULE_DESCRIPTION("");// 模块描述