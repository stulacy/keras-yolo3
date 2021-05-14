#########################
# Runs the yolo3 license plate recognition software
# using Keras.
#
# Args:
#   1: Video file
#   2: Output dir
full_path="$(realpath $1)"
python predict.py -c zoo/config_license_plates.json -i $full_path -o $2
