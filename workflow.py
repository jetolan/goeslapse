import os
import shutil

import rgb_frame
import movie
import pandas as pd

if __name__ == "__main__":
    sat = 'goes17'
    bands = [1, 2, 3]  # 1:blue, 2:red, 3:nir
    frame = 'F'
    local_dir = "/Users/jetolan/data/goes/"


    # TODO: in UTC - convert to Pacific
    start_date = '2021-09-13 11:00'
    end_date = '2021-09-16 07:00'

    start_date = '2021-06-13 20:00'
    end_date = '2021-06-14 11:00'

    start_date = '2021-06-13 19:50'
    end_date = '2021-06-13 20:00'
    #end_date = '2021-06-15 16:30'

    dates = pd.date_range(start_date, end_date, freq="10min")


    # TODO: could stream directly to writer; avoid disk space for all images
    frame_files = []
    for date in dates:
        frame_files.append(
            rgb_frame.main(date, sat, bands, frame,
                           local_dir, clean=True, uselocal=True))
    movie_name = f"{local_dir}{start_date}_{end_date}.mkv"
    movie_name = movie_name.replace(':', '-').replace(' ', '-')
    movie.main(frame_files, movie_name)
