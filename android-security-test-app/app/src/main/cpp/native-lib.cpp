#include <jni.h>
#include <string>
#include <android/log.h>

#define LOG_TAG "NativeCrypto"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

static const char XOR_KEY[] = "FridaHookTest2024!@#";
static const int XOR_KEY_LEN = 20;

static void xor_cipher(unsigned char *data, int data_len, const unsigned char *key, int key_len) {
    for (int i = 0; i < data_len; i++) {
        data[i] ^= key[i % key_len];
    }
}

static char *hex_encode(const unsigned char *data, int len) {
    char *hex = new char[len * 2 + 1];
    for (int i = 0; i < len; i++) {
        sprintf(hex + i * 2, "%02x", data[i]);
    }
    hex[len * 2] = '\0';
    return hex;
}

static int hex_decode(const char *hex, unsigned char *out, int out_size) {
    int len = strlen(hex);
    if (len % 2 != 0 || len / 2 > out_size) return -1;
    for (int i = 0; i < len / 2; i++) {
        unsigned int byte;
        sscanf(hex + i * 2, "%02x", &byte);
        out[i] = (unsigned char) byte;
    }
    return len / 2;
}

static unsigned int simple_hash(const char *data, int len) {
    unsigned int hash = 5381;
    for (int i = 0; i < len; i++) {
        hash = ((hash << 5) + hash) + (unsigned char) data[i];
    }
    return hash;
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_test_fridahook_native_1lib_NativeCrypto_encrypt(
        JNIEnv *env, jclass clazz, jstring input) {
    if (input == nullptr) {
        return env->NewStringUTF("");
    }

    const char *input_str = env->GetStringUTFChars(input, nullptr);
    int input_len = strlen(input_str);

    LOGD("encrypt() input=%s len=%d", input_str, input_len);

    unsigned char *buffer = new unsigned char[input_len];
    memcpy(buffer, input_str, input_len);

    xor_cipher(buffer, input_len, (const unsigned char *) XOR_KEY, XOR_KEY_LEN);

    char *hex = hex_encode(buffer, input_len);

    LOGD("encrypt() result=%s", hex);

    delete[] buffer;
    env->ReleaseStringUTFChars(input, input_str);

    jstring result = env->NewStringUTF(hex);
    delete[] hex;
    return result;
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_test_fridahook_native_1lib_NativeCrypto_decrypt(
        JNIEnv *env, jclass clazz, jstring encrypted) {
    if (encrypted == nullptr) {
        return env->NewStringUTF("");
    }

    const char *hex_str = env->GetStringUTFChars(encrypted, nullptr);
    int hex_len = strlen(hex_str);

    LOGD("decrypt() input=%s len=%d", hex_str, hex_len);

    int data_len = hex_len / 2;
    unsigned char *buffer = new unsigned char[data_len + 1];

    int decoded = hex_decode(hex_str, buffer, data_len);
    if (decoded < 0) {
        delete[] buffer;
        env->ReleaseStringUTFChars(encrypted, hex_str);
        return env->NewStringUTF("Invalid hex string");
    }

    xor_cipher(buffer, data_len, (const unsigned char *) XOR_KEY, XOR_KEY_LEN);
    buffer[data_len] = '\0';

    LOGD("decrypt() result=%s", (char *) buffer);

    jstring result = env->NewStringUTF((char *) buffer);
    delete[] buffer;
    env->ReleaseStringUTFChars(encrypted, hex_str);
    return result;
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_test_fridahook_native_1lib_NativeCrypto_sign(
        JNIEnv *env, jclass clazz, jstring data) {
    if (data == nullptr) {
        return env->NewStringUTF("");
    }

    const char *data_str = env->GetStringUTFChars(data, nullptr);
    int data_len = strlen(data_str);

    LOGD("sign() data=%s len=%d", data_str, data_len);

    unsigned int h1 = simple_hash(data_str, data_len);
    unsigned int h2 = simple_hash(XOR_KEY, XOR_KEY_LEN);
    unsigned int sig = h1 ^ h2;

    unsigned char sig_bytes[4];
    sig_bytes[0] = (sig >> 24) & 0xFF;
    sig_bytes[1] = (sig >> 16) & 0xFF;
    sig_bytes[2] = (sig >> 8) & 0xFF;
    sig_bytes[3] = sig & 0xFF;

    char *hex = hex_encode(sig_bytes, 4);

    LOGD("sign() result=%s", hex);

    env->ReleaseStringUTFChars(data, data_str);

    jstring result = env->NewStringUTF(hex);
    delete[] hex;
    return result;
}

extern "C" JNIEXPORT jboolean JNICALL
Java_com_test_fridahook_native_1lib_NativeCrypto_verifySignature(
        JNIEnv *env, jclass clazz, jstring data, jstring signature) {
    if (data == nullptr || signature == nullptr) {
        return JNI_FALSE;
    }

    const char *data_str = env->GetStringUTFChars(data, nullptr);
    const char *sig_str = env->GetStringUTFChars(signature, nullptr);

    LOGD("verifySignature() data=%s signature=%s", data_str, sig_str);

    jclass clazz_ref = env->FindClass("com/test/fridahook/native_lib/NativeCrypto");
    jmethodID sign_method = env->GetStaticMethodID(clazz_ref, "sign",
                                                     "(Ljava/lang/String;)Ljava/lang/String;");
    jstring expected_sig = (jstring) env->CallStaticObjectMethod(clazz_ref, sign_method, data);
    const char *expected_str = env->GetStringUTFChars(expected_sig, nullptr);

    bool valid = strcmp(expected_str, sig_str) == 0;

    LOGD("verifySignature() expected=%s actual=%s valid=%d", expected_str, sig_str, valid);

    env->ReleaseStringUTFChars(data, data_str);
    env->ReleaseStringUTFChars(signature, sig_str);
    env->ReleaseStringUTFChars(expected_sig, expected_str);

    return valid ? JNI_TRUE : JNI_FALSE;
}
