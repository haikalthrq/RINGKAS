using Microsoft.AspNetCore.Identity;

namespace Ringkas.Api.Auth;

public sealed class IdentityRoleSeeder(RoleManager<IdentityRole> roleManager)
{
    public async Task SeedAsync(CancellationToken cancellationToken = default)
    {
        foreach (var roleName in AppRoles.All)
        {
            if (await roleManager.RoleExistsAsync(roleName))
            {
                continue;
            }

            var result = await roleManager.CreateAsync(new IdentityRole(roleName));
            if (!result.Succeeded)
            {
                throw new InvalidOperationException(
                    $"Failed to seed Identity role '{roleName}': {string.Join(", ", result.Errors.Select(error => error.Description))}");
            }
        }
    }
}
