import imageio
import glob
import os


def main(frame_files, movie_name=None):
    if movie_name is None:
        movie_name = f"{os.path.dirname(frame_files[0])}/goes.mp4"

    with imageio.get_writer(movie_name,
                            mode='I',
                            fps=18,
                            codec='libx265',
                            quality=3,
                            # pixelformat='yuv44p'
                            ) as writer:
        for ff in frame_files:
            print(ff)
            image = imageio.imread(ff)
            writer.append_data(image)


if __name__ == "__main__":
    files = sorted(glob.glob('/Users/jetolan/goes/*.jpg'))
    files = files[0:]
    main(files)
