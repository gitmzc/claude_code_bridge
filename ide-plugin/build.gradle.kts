plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "1.9.21"
    id("org.jetbrains.intellij.platform") version "2.2.1"
}

group = "com.ccb"
version = "0.2.0"

repositories {
    mavenCentral()
    intellijPlatform {
        defaultRepositories()
    }
}

dependencies {
    implementation("com.google.code.gson:gson:2.10.1")

    intellijPlatform {
        // Use local IntelliJ IDEA installation if available, fallback to download
        val localIdePath = file("/Applications/IntelliJ IDEA CE.app")
        val localIdeaUltimatePath = file("/Applications/IntelliJ IDEA.app")
        
        if (localIdePath.exists()) {
            local(localIdePath)
        } else if (localIdeaUltimatePath.exists()) {
            local(localIdeaUltimatePath)
        } else {
            intellijIdeaCommunity("2023.2.5")
        }
        bundledPlugin("org.jetbrains.plugins.terminal")
    }
}

tasks {
    withType<JavaCompile> {
        sourceCompatibility = "17"
        targetCompatibility = "17"
    }
    withType<org.jetbrains.kotlin.gradle.tasks.KotlinCompile> {
        kotlinOptions.jvmTarget = "17"
    }

    patchPluginXml {
        sinceBuild.set("232")
        untilBuild.set("251.*")
    }

    signPlugin {
        certificateChain.set(System.getenv("CERTIFICATE_CHAIN"))
        privateKey.set(System.getenv("PRIVATE_KEY"))
        password.set(System.getenv("PRIVATE_KEY_PASSWORD"))
    }

    publishPlugin {
        token.set(System.getenv("PUBLISH_TOKEN"))
    }
}
