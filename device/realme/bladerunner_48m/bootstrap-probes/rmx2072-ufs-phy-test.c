// SPDX-License-Identifier: GPL-2.0-only
// Isolated SM8250 PHY control. Both binds are explicit from the RAM-only shell.
#include <linux/delay.h>
#include <linux/init.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/phy/phy.h>
#include <linux/platform_device.h>
#include <linux/reset.h>

static int rmx_phy_bus_probe(struct platform_device *pdev)
{
	if (!of_device_is_compatible(pdev->dev.of_node, "realme,rmx2072-diag-ufs-phy-bus"))
		return -ENODEV;
	return devm_of_platform_populate(&pdev->dev);
}

static int rmx_phy_test_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct reset_control *rst;
	struct phy *phy;
	int ret, cleanup;

	if (!of_device_is_compatible(dev->of_node, "realme,rmx2072-diag-ufs-phy-test"))
		return -ENODEV;
	phy = devm_phy_get(dev, "ufsphy");
	if (IS_ERR(phy))
		return dev_err_probe(dev, PTR_ERR(phy), "get ufsphy\n");
	rst = devm_reset_control_get_exclusive(dev, "rst");
	if (IS_ERR(rst))
		return dev_err_probe(dev, PTR_ERR(rst), "get GCC UFS block reset\n");

	/* Match the GCC core-reset pulse and settle time in ufs_qcom_host_reset. */
	dev_info(dev, "PHY trial: begin GCC reset\n");
	ret = reset_control_assert(rst);
	if (ret)
		return dev_err_probe(dev, ret, "assert GCC reset\n");
	usleep_range(200, 210);
	ret = reset_control_deassert(rst);
	if (ret)
		return dev_err_probe(dev, ret, "deassert GCC reset\n");
	usleep_range(1000, 1100);
	ret = phy_init(phy);
	if (ret)
		return dev_err_probe(dev, ret, "phy_init\n");
	dev_info(dev, "PHY trial: init passed\n");
	ret = phy_set_mode_ext(phy, PHY_MODE_UFS_HS_B, 3);
	if (ret) {
		dev_err(dev, "set HS-B G3: %d\n", ret);
		goto exit_phy;
	}
	ret = phy_power_on(phy);
	if (ret) {
		dev_err(dev, "phy_power_on: %d\n", ret);
		goto exit_phy;
	}
	dev_info(dev, "PHY trial: power_on passed, calibrating HS-B G3\n");
	ret = phy_calibrate(phy);
	if (ret)
		dev_err(dev, "phy_calibrate: %d\n", ret);
	else
		dev_info(dev, "PHY trial: PCS_READY passed\n");
	cleanup = phy_power_off(phy);
	if (cleanup) {
		dev_err(dev, "phy_power_off: %d\n", cleanup);
		if (!ret)
			ret = cleanup;
	}
exit_phy:
	cleanup = phy_exit(phy);
	if (cleanup) {
		dev_err(dev, "phy_exit: %d\n", cleanup);
		if (!ret)
			ret = cleanup;
	}
	if (!ret)
		dev_info(dev, "PHY trial: power_off and exit passed\n");
	return ret;
}

static struct platform_driver rmx_phy_bus_driver = {
	.probe = rmx_phy_bus_probe,
	.driver.name = "rmx2072-ufs-phy-bus",
};

static struct platform_driver rmx_phy_test_driver = {
	.probe = rmx_phy_test_probe,
	.driver.name = "rmx2072-ufs-phy-test",
};

static int __init rmx_phy_test_init(void)
{
	int ret;

	ret = platform_driver_register(&rmx_phy_bus_driver);
	if (ret)
		return ret;
	ret = platform_driver_register(&rmx_phy_test_driver);
	if (ret)
		platform_driver_unregister(&rmx_phy_bus_driver);
	return ret;
}
device_initcall(rmx_phy_test_init);
