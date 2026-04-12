package com.test.fridahook.native_lib;

public class NativeCrypto {

    static {
        System.loadLibrary("native-lib");
    }

    public static native String encrypt(String input);

    public static native String decrypt(String encrypted);

    public static native String sign(String data);

    public static native boolean verifySignature(String data, String signature);
}
