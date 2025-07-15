import matplotlib as mpl

mpl.use('WxAgg')

import matplotlib.pyplot as plt

plt.plot(range(10), range(10)[::-1])
plt.show()
