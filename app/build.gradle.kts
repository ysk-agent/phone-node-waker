plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.google.gms.google-services")
}

android {
    namespace = "dev.moriya.phonenode.waker"
    compileSdk = 35

    defaultConfig {
        applicationId = "dev.moriya.phonenode.waker"
        minSdk = 29
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
    }

    // Pinned signing key, same pattern as yt-player: CI decodes the
    // keystore from the SIGNING_KEYSTORE_B64 repo secret and points
    // SIGNING_KEYSTORE at it, so every build carries the same
    // certificate and can overwrite-install over previous builds.
    signingConfigs {
        create("pinned") {
            val keystorePath = System.getenv("SIGNING_KEYSTORE")
            if (keystorePath != null) {
                storeFile = file(keystorePath)
                storePassword = System.getenv("SIGNING_STORE_PASS")
                keyAlias = System.getenv("SIGNING_KEY_ALIAS")
                keyPassword = System.getenv("SIGNING_KEY_PASS")
            }
        }
    }

    buildTypes {
        debug {
            if (System.getenv("SIGNING_KEYSTORE") != null) {
                signingConfig = signingConfigs.getByName("pinned")
            }
        }
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation(platform("com.google.firebase:firebase-bom:33.7.0"))
    implementation("com.google.firebase:firebase-messaging")
}
