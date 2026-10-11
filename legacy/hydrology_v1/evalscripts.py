
NDVI = """
// VERSION 3

function setup() {
    
    return { input: ["B04", "B08"], output: { bands: 1, sampleType: "FLOAT32"} };
}
function evaluatePixel(sample) {
    let ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04);
    return [ndvi];
}

"""
