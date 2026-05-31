// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "TrustShieldSDK",
    platforms: [.iOS(.v16), .macOS(.v13)],
    products: [
        .library(name: "TrustShieldSDK", targets: ["TrustShieldSDK"]),
    ],
    targets: [
        .target(
            name: "TrustShieldSDK",
            path: "Sources"
        ),
    ]
)
